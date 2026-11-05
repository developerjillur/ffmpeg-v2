/* Excluded diagnostic: per-thread CPU and pthread waits; one video encoder. */
#include <stdint.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <pthread.h>
#include <pthread/qos.h>
#include <sched.h>
#include <time.h>
#include <unistd.h>
#include <libproc.h>
#include <sys/resource.h>
#include <mach/mach_time.h>
#include <mach-o/dyld.h>
#include <errno.h>
#include <x264.h>

struct locksite { uintptr_t caller;uint64_t calls,contended,wait_ns; };
struct worker {
    uint64_t id, started, cpu_started, condition_ns, mutex_ns, condition_calls, mutex_calls;
    uint64_t condition_max_ns, mutex_max_ns;
    struct locksite sites[16];
    unsigned last_site;
    uint64_t overflow_sites;
    const char *library;
    const char *symbol;
    uintptr_t offset;
    unsigned slot;
};
static int trace_fd = -1;
static atomic_uint slots;
static _Thread_local struct worker *current;
static _Thread_local int in_hook;
static struct worker main_worker;
static uint64_t process_started, encoder_call_ns, feed_gap_ns, encoder_return_ns;
static unsigned input_frames, encoder_calls;
static struct rusage_info_v6 initial_usage;
static int usage_supported;

static uint64_t wall_ns(void) { return clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW); }
static uint64_t cpu_ns(void) { return clock_gettime_nsec_np(CLOCK_THREAD_CPUTIME_ID); }

static unsigned qos(void) {
    qos_class_t value=QOS_CLASS_UNSPECIFIED;
    int relative=0;
    pthread_get_qos_class_np(pthread_self(),&value,&relative);
    return value;
}

static void write_worker(struct worker *w) {
    in_hook=1;
    char name[64]={0};
    pthread_getname_np(pthread_self(),name,sizeof(name));
    uint64_t wall=wall_ns()-w->started, cpu=cpu_ns()-w->cpu_started;
    /* Thread names in this bounded corpus contain no JSON control characters. */
    for (unsigned i=0;i<sizeof(name) && name[i];i++)
        if ((unsigned char)name[i]<32 || name[i]=='"' || name[i]=='\\') name[i]='_';
    if (trace_fd>=0)
        dprintf(trace_fd,"{\"event\":\"worker\",\"slot\":%u,\"id\":%llu,\"library\":\"%s\",\"symbol\":\"%s\",\"offset\":%lu,\"name\":\"%s\",\"qos\":%u,\"wall_ns\":%llu,\"cpu_ns\":%llu,\"condition_ns\":%llu,\"mutex_ns\":%llu,\"condition_calls\":%llu,\"mutex_calls\":%llu,\"condition_max_ns\":%llu,\"mutex_max_ns\":%llu,\"overflow_sites\":%llu}\n",
                w->slot,(unsigned long long)w->id,w->library?w->library:"",w->symbol?w->symbol:"",(unsigned long)w->offset,
                name,qos(),(unsigned long long)wall,(unsigned long long)cpu,(unsigned long long)w->condition_ns,
                (unsigned long long)w->mutex_ns,(unsigned long long)w->condition_calls,(unsigned long long)w->mutex_calls,
                (unsigned long long)w->condition_max_ns,(unsigned long long)w->mutex_max_ns,(unsigned long long)w->overflow_sites);
    for (unsigned i=0;i<16;i++) if (w->sites[i].calls) {
        struct locksite *site=&w->sites[i];Dl_info info={0};dladdr((void *)site->caller,&info);
        dprintf(trace_fd,"{\"event\":\"mutex_site\",\"slot\":%u,\"library\":\"%s\",\"symbol\":\"%s\",\"offset\":%lu,\"calls\":%llu,\"contended\":%llu,\"wait_ns\":%llu}\n",w->slot,info.dli_fname?info.dli_fname:"",info.dli_sname?info.dli_sname:"",(unsigned long)(site->caller-(uintptr_t)info.dli_fbase),(unsigned long long)site->calls,(unsigned long long)site->contended,(unsigned long long)site->wait_ns);
    }
    in_hook=0;
}

__attribute__((constructor)) static void begin_trace(void) {
    process_started=wall_ns();
    const char *path=getenv("FFV2_WORKER_TRACE");
    if (path) trace_fd=open(path,O_WRONLY|O_CREAT|O_EXCL|O_APPEND,0600);
    if (trace_fd<0) return;
    usage_supported=proc_pid_rusage(getpid(),RUSAGE_INFO_V6,(rusage_info_t *)&initial_usage)==0;
    main_worker.started=wall_ns();main_worker.cpu_started=cpu_ns();main_worker.library="main";
    pthread_threadid_np(NULL,&main_worker.id);current=&main_worker;
    dprintf(trace_fd,"{\"event\":\"load\",\"pid\":%d,\"rusage_v6\":%s,\"clock_thread_cpu\":%llu}\n",getpid(),usage_supported?"true":"false",(unsigned long long)cpu_ns());
    for (uint32_t i=0;i<_dyld_image_count();i++) {
        const char *name=_dyld_get_image_name(i);
        if (name && strstr(name,"libx264"))
            dprintf(trace_fd,"{\"event\":\"encoder_image\",\"path\":\"%s\"}\n",name);
    }
}

__attribute__((destructor)) static void end_trace(void) {
    if (trace_fd<0) return;
    write_worker(&main_worker);
    struct rusage_info_v6 final={0};
    int ok=usage_supported && proc_pid_rusage(getpid(),RUSAGE_INFO_V6,(rusage_info_t *)&final)==0;
    mach_timebase_info_data_t scale;
    mach_timebase_info(&scale);
    dprintf(trace_fd,"{\"event\":\"process_lifetime\",\"wall_mach\":%llu,\"user_mach\":%llu,\"system_mach\":%llu,\"p_user_mach\":%llu,\"p_system_mach\":%llu,\"runnable_mach\":%llu,\"instructions\":%llu,\"cycles\":%llu,\"page_wait_mach\":%llu,\"pageins\":%llu,\"startup_cpu_mach\":%llu,\"startup_page_wait_mach\":%llu,\"startup_pageins\":%llu}\n",
            (unsigned long long)(mach_absolute_time()-final.ri_proc_start_abstime),
            (unsigned long long)final.ri_user_time,(unsigned long long)final.ri_system_time,
            (unsigned long long)final.ri_user_ptime,(unsigned long long)final.ri_system_ptime,
            (unsigned long long)final.ri_runnable_time,(unsigned long long)final.ri_instructions,
            (unsigned long long)final.ri_cycles,(unsigned long long)final.ri_page_wait_time_mach,
            (unsigned long long)final.ri_pageins,(unsigned long long)(initial_usage.ri_user_time+initial_usage.ri_system_time),
            (unsigned long long)initial_usage.ri_page_wait_time_mach,(unsigned long long)initial_usage.ri_pageins);
    dprintf(trace_fd,"{\"event\":\"process\",\"input_frames\":%u,\"encoder_calls\":%u,\"observed_wall_ns\":%llu,\"encode_call_ns\":%llu,\"feed_gap_ns\":%llu,\"rusage_v6\":%s,\"user_mach\":%llu,\"system_mach\":%llu,\"p_user_mach\":%llu,\"p_system_mach\":%llu,\"instructions\":%llu,\"cycles\":%llu,\"p_instructions\":%llu,\"p_cycles\":%llu,\"runnable_raw\":%llu,\"page_wait_mach\":%llu,\"pageins\":%llu,\"disk_read_bytes\":%llu,\"mach_numer\":%u,\"mach_denom\":%u}\n",
            input_frames,encoder_calls,(unsigned long long)(wall_ns()-process_started),(unsigned long long)encoder_call_ns,
            (unsigned long long)feed_gap_ns,ok?"true":"false",
            (unsigned long long)(final.ri_user_time-initial_usage.ri_user_time),
            (unsigned long long)(final.ri_system_time-initial_usage.ri_system_time),
            (unsigned long long)(final.ri_user_ptime-initial_usage.ri_user_ptime),
            (unsigned long long)(final.ri_system_ptime-initial_usage.ri_system_ptime),
            (unsigned long long)(final.ri_instructions-initial_usage.ri_instructions),
            (unsigned long long)(final.ri_cycles-initial_usage.ri_cycles),
            (unsigned long long)(final.ri_pinstructions-initial_usage.ri_pinstructions),
            (unsigned long long)(final.ri_pcycles-initial_usage.ri_pcycles),
            (unsigned long long)(final.ri_runnable_time-initial_usage.ri_runnable_time),
            (unsigned long long)(final.ri_page_wait_time_mach-initial_usage.ri_page_wait_time_mach),
            (unsigned long long)(final.ri_pageins-initial_usage.ri_pageins),
            (unsigned long long)(final.ri_diskio_bytesread-initial_usage.ri_diskio_bytesread),scale.numer,scale.denom);
}

struct entry { void *(*routine)(void *);void *argument;struct worker worker; };
static void finish_worker(void *opaque) { write_worker(opaque);current=NULL; }
static void *thread_entry(void *opaque) {
    struct entry value=*(struct entry *)opaque;free(opaque);
    struct worker *w=&value.worker;
    w->started=wall_ns();w->cpu_started=cpu_ns();pthread_threadid_np(NULL,&w->id);current=w;
    void *result;
    pthread_cleanup_push(finish_worker,w);
    result=value.routine(value.argument);
    pthread_cleanup_pop(1);
    return result;
}

static int probe_create(pthread_t *thread,const pthread_attr_t *attribute,void *(*routine)(void *),void *argument) {
    if (trace_fd<0) return pthread_create(thread,attribute,routine,argument);
    struct entry *value=calloc(1,sizeof(*value));
    if (!value) return pthread_create(thread,attribute,routine,argument);
    Dl_info info={0};dladdr((const void *)routine,&info);
    value->routine=routine;value->argument=argument;value->worker.library=info.dli_fname;
    value->worker.symbol=info.dli_sname;value->worker.offset=(uintptr_t)routine-(uintptr_t)info.dli_fbase;
    value->worker.slot=atomic_fetch_add(&slots,1)+1;
    int result=pthread_create(thread,attribute,thread_entry,value);
    if (result) free(value);
    return result;
}

static int probe_cond(pthread_cond_t *cond,pthread_mutex_t *mutex) {
    if (!current || in_hook) return pthread_cond_wait(cond,mutex);
    uint64_t before=wall_ns();in_hook=1;int result=pthread_cond_wait(cond,mutex);in_hook=0;uint64_t elapsed=wall_ns()-before;
    current->condition_ns+=elapsed;current->condition_calls++;
    if (elapsed>current->condition_max_ns) current->condition_max_ns=elapsed;
    return result;
}
static int probe_timed_cond(pthread_cond_t *cond,pthread_mutex_t *mutex,const struct timespec *limit) {
    if (!current || in_hook) return pthread_cond_timedwait(cond,mutex,limit);
    uint64_t before=wall_ns();in_hook=1;int result=pthread_cond_timedwait(cond,mutex,limit);in_hook=0;uint64_t elapsed=wall_ns()-before;
    current->condition_ns+=elapsed;current->condition_calls++;
    if (elapsed>current->condition_max_ns) current->condition_max_ns=elapsed;
    return result;
}
static int probe_mutex(pthread_mutex_t *mutex) {
    if (!current || in_hook) return pthread_mutex_lock(mutex);
    uintptr_t caller=(uintptr_t)__builtin_return_address(0);struct locksite *site=&current->sites[current->last_site];
    if (site->caller!=caller) {
        site=NULL;
        for (unsigned i=0;i<16;i++) if (current->sites[i].caller==caller || !current->sites[i].caller) {
            site=&current->sites[i];site->caller=caller;current->last_site=i;break;
        }
    }
    current->mutex_calls++;if (site) site->calls++;else current->overflow_sites++;
    int result=pthread_mutex_trylock(mutex);
    if (result!=EBUSY) return result;
    uint64_t before=wall_ns();result=pthread_mutex_lock(mutex);uint64_t elapsed=wall_ns()-before;
    if (site) {site->contended++;site->wait_ns+=elapsed;}
    current->mutex_ns+=elapsed;
    if (elapsed>current->mutex_max_ns) current->mutex_max_ns=elapsed;
    return result;
}

static x264_t *probe_open(x264_param_t *parameter) {
    x264_t *encoder=x264_encoder_open(parameter);
    if (encoder && trace_fd>=0) {
        x264_param_t actual;x264_encoder_parameters(encoder,&actual);
        Dl_info info={0};dladdr((const void *)x264_encoder_parameters,&info);
        dprintf(trace_fd,"{\"event\":\"encoder\",\"threads\":%d,\"lookahead_threads\":%d,\"sync_lookahead\":%d,\"cpu\":%u,\"parameter_library\":\"%s\"}\n",actual.i_threads,actual.i_lookahead_threads,actual.i_sync_lookahead,actual.cpu,info.dli_fname?info.dli_fname:"");
    }
    return encoder;
}
static int probe_encode(x264_t *encoder,x264_nal_t **nals,int *count,x264_picture_t *input,x264_picture_t *output) {
    uint64_t before=wall_ns();
    if (encoder_return_ns) feed_gap_ns+=before-encoder_return_ns;
    if (input) input_frames++;
    int result=x264_encoder_encode(encoder,nals,count,input,output);
    encoder_return_ns=wall_ns();encoder_call_ns+=encoder_return_ns-before;encoder_calls++;
    return result;
}
#define INTERPOSE(replacement, original, name) \
__attribute__((used,section("__DATA,__interpose"))) static const struct { const void *new_function;const void *old_function; } name={(const void *)(replacement),(const void *)(original)}
#ifndef FFV2_PROCESS_ONLY
INTERPOSE(probe_create,pthread_create,create_pair);
INTERPOSE(probe_cond,pthread_cond_wait,cond_pair);
INTERPOSE(probe_timed_cond,pthread_cond_timedwait,timed_cond_pair);
INTERPOSE(probe_mutex,pthread_mutex_lock,mutex_pair);
#endif
INTERPOSE(probe_open,x264_encoder_open,open_pair);
INTERPOSE(probe_encode,x264_encoder_encode,encode_pair);
