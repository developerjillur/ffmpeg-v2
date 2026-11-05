/* Owned-process wall clock, hot-file residency and external CPU observations. */
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/event.h>
#include <sys/wait.h>
#include <mach/mach.h>
#include <mach/mach_time.h>
#include <mach/processor_info.h>
#include <libproc.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <spawn.h>
#include <math.h>

extern char **environ;

enum { MAX_SAMPLES=8192 };
struct sample {
    uint64_t at, ticks[4], cpu, child_cpu, loads, monitor;
};
static struct sample samples[MAX_SAMPLES];
static unsigned nsamples;
static volatile sig_atomic_t stopped;
static mach_timebase_info_data_t timebase;
static mach_port_t host;
static pid_t media=-1,load_pid[2]={-1,-1};
static int load_count;
struct image { void *mapping;size_t size;int fd; };
static struct image images[128];
static unsigned image_count;
static size_t image_bytes;
static void stopping(int sig) { (void)sig;stopped=1; }
static double seconds(uint64_t value) { return (double)value*timebase.numer/timebase.denom/1e9; }
static uint64_t cpu(struct rusage_info_v6 *r) { return r->ri_user_time+r->ri_system_time; }
static int usage(pid_t pid,struct rusage_info_v6 *r) { return proc_pid_rusage(pid,RUSAGE_INFO_V6,(rusage_info_t *)r); }
static void pause_ms(unsigned ms) { struct timespec t={ms/1000,(ms%1000)*1000000};nanosleep(&t,NULL); }
static int absolute(const char *path) { return path && path[0]=='/'; }

static int snapshot(struct sample *s,int include_media) {
    processor_info_array_t info=NULL;mach_msg_type_number_t count=0;natural_t processors=0;
    if (host_processor_info(host,PROCESSOR_CPU_LOAD_INFO,&processors,&info,&count)!=KERN_SUCCESS) return -1;
    if (!processors || processors>64 || count!=processors*CPU_STATE_MAX) {
        vm_deallocate(mach_task_self(),(vm_address_t)info,count*sizeof(integer_t));return -1;
    }
    s->at=mach_absolute_time();for (int i=0;i<4;i++) {
        s->ticks[i]=0;
        for (natural_t j=0;j<processors;j++) s->ticks[i]+=(uint32_t)info[j*CPU_STATE_MAX+i];
    }
    vm_deallocate(mach_task_self(),(vm_address_t)info,count*sizeof(integer_t));
    struct rusage_info_v6 r={0};
    if (include_media) {
        if (usage(media,&r)) return -1;
        s->cpu=cpu(&r);s->child_cpu=r.ri_child_user_time+r.ri_child_system_time;
    }
    for (int i=0;i<load_count;i++) {
        siginfo_t ended={0};
        if (waitid(P_PID,(id_t)load_pid[i],&ended,WEXITED|WNOHANG|WNOWAIT) || ended.si_pid || usage(load_pid[i],&r)) return -1;
        s->loads+=cpu(&r);
    }
    if (usage(getpid(),&r)) return -1;s->monitor=cpu(&r);
    return 0;
}

static double background(struct sample *a,struct sample *b,int include_media) {
    double wall=seconds(b->at-a->at),busy=0;
    for (int i=0;i<4;i++) if (i!=CPU_STATE_IDLE) busy+=(uint32_t)(b->ticks[i]-a->ticks[i]);
    double own=seconds(b->loads-a->loads)+seconds(b->monitor-a->monitor);
    if (include_media) own+=seconds(b->cpu-a->cpu);
    return busy/sysconf(_SC_CLK_TCK)/wall-own/wall;
}

static uint64_t residency(void *mapping,size_t size,long page) {
    size_t count=(size+(size_t)page-1)/(size_t)page;unsigned char *vector=calloc(count,1);
    if (!vector) return UINT64_MAX;
    if (mincore(mapping,size,(char *)vector)) { free(vector);return UINT64_MAX; }
    uint64_t resident=0;
    for (size_t i=0;i<count;i++) if ((vector[i]&MINCORE_INCORE) && !(vector[i]&MINCORE_PAGED_OUT)) resident++;
    free(vector);return resident;
}

static int prepare_images(long page) {
    const char *path=getenv("FFV2_BENCH_IMAGES");if (!path) return 0;
    FILE *list=fopen(path,"r");if (!list) return -1;char name[4096];int result=0;
    while (fgets(name,sizeof(name),list)) {
        size_t length=strlen(name);if (length && name[length-1]=='\n') name[--length]=0;
        if (!length || name[0]!='/' || length>=sizeof(name)-1 || image_count>=128) { result=-1;break; }
        int fd=open(name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);struct stat meta;
        if (fd<0) { result=-1;break; }
        if (fstat(fd,&meta) || !S_ISREG(meta.st_mode) || meta.st_size<1 || (uint64_t)meta.st_size>256*1024*1024-image_bytes) {
            close(fd);result=-1;break;
        }
        void *mapping=mmap(NULL,(size_t)meta.st_size,PROT_READ,MAP_PRIVATE,fd,0);
        if (mapping==MAP_FAILED) { close(fd);result=-1;break; }
        if (mlock(mapping,(size_t)meta.st_size)) { munmap(mapping,(size_t)meta.st_size);close(fd);result=-1;break; }
        images[image_count++]=(struct image){mapping,(size_t)meta.st_size,fd};image_bytes+=(size_t)meta.st_size;
        if (residency(mapping,(size_t)meta.st_size,page)!=(meta.st_size+page-1)/(size_t)page) { result=-1;break; }
    }
    fclose(list);return result;
}

static int images_resident(long page) {
    for (unsigned i=0;i<image_count;i++)
        if (residency(images[i].mapping,images[i].size,page)!=(images[i].size+page-1)/(size_t)page) return 0;
    return image_count>0;
}

static void terminate_owned(void) {
    if (media>0) { kill(media,SIGCONT);kill(media,SIGTERM); }
    for (int i=0;i<load_count;i++) if (load_pid[i]>0) kill(load_pid[i],SIGTERM);
    for (int attempt=0;attempt<50;attempt++) {
        int remaining=0;
        if (media>0 && waitpid(media,NULL,WNOHANG)==media) media=-1;
        if (media>0) remaining++;
        for (int i=0;i<load_count;i++) if (load_pid[i]>0) {
            if (waitpid(load_pid[i],NULL,WNOHANG)==load_pid[i]) load_pid[i]=-1;
            else remaining++;
        }
        if (!remaining) break;pause_ms(100);
    }
    if (media>0) {
        if (waitpid(media,NULL,WNOHANG)==0) { kill(media,SIGKILL);waitpid(media,NULL,0); }
        media=-1;
    }
    for (int i=0;i<load_count;i++) if (load_pid[i]>0) {
        if (waitpid(load_pid[i],NULL,WNOHANG)==0) { kill(load_pid[i],SIGKILL);waitpid(load_pid[i],NULL,0); }
        load_pid[i]=-1;
    }
}

int main(int argc,char **argv) {
    /* counter input load-count load-binary owner-pid max-background -- command */
    if (argc<9 || strcmp(argv[7],"--") || !absolute(argv[1]) || !absolute(argv[2]) ||
        !absolute(argv[4]) || !absolute(argv[8])) return 2;
    char *end=NULL;long loads=strtol(argv[3],&end,10);
    if (end==argv[3] || *end || (loads!=0 && loads!=2)) return 3;load_count=(int)loads;
    pid_t owner=(pid_t)strtol(argv[5],&end,10);if (end==argv[5] || *end || (owner && owner!=getppid())) return 4;
    if (!owner) owner=getppid();if (owner<2) return 4;
    double max_background=strtod(argv[6],&end);if (end==argv[6] || *end || !isfinite(max_background) || max_background< -1 || max_background>sysconf(_SC_NPROCESSORS_ONLN)+.5) return 5;
    int fd=open(argv[1],O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if (fd<0) return 6;
    FILE *report=fdopen(fd,"w");if (!report) { close(fd);return 7; }
    signal(SIGTERM,stopping);signal(SIGINT,stopping);mach_timebase_info(&timebase);host=mach_host_self();
    int source=open(argv[2],O_RDONLY|O_NOFOLLOW|O_CLOEXEC);struct stat before,after;
    if (source<0 || fstat(source,&before) || !S_ISREG(before.st_mode) || before.st_size<1 || before.st_size>INT64_C(3221225472)) {
        fprintf(report,"{\"status\":\"failed\",\"reason\":\"input_bound\"}\n");fclose(report);return 8;
    }
    size_t size=(size_t)before.st_size;long page=sysconf(_SC_PAGESIZE);size_t pages=(size+page-1)/page;
    void *mapping=mmap(NULL,size,PROT_READ,MAP_SHARED,source,0);
    if (mapping==MAP_FAILED) { close(source);fclose(report);return 9; }
    struct rusage_info_v6 warm_before={0},warm_after={0};usage(getpid(),&warm_before);uint64_t warm_start=mach_absolute_time();
    unsigned char *buffer=malloc(8*1024*1024);if (!buffer) { munmap(mapping,size);close(source);fclose(report);return 10; }
    off_t offset=0;
    while (offset<before.st_size && !stopped && getppid()==owner) {
        size_t count=(size_t)(before.st_size-offset);if (count>8*1024*1024) count=8*1024*1024;
        ssize_t got=pread(source,buffer,count,offset);
        if (got<0 && errno==EINTR) continue;
        if (got<=0) break;offset+=got;
    }
    free(buffer);volatile uint64_t touch=0;
    if (offset==before.st_size) for (size_t i=0;i<size;i+=(size_t)page) touch+=((volatile unsigned char *)mapping)[i];
    int cache_locked=offset==before.st_size && !stopped && mlock(mapping,size)==0;
    int lock_error=cache_locked?0:errno;
    int images_prepared=prepare_images(page)==0;
    uint64_t resident_before=residency(mapping,size,page);usage(getpid(),&warm_after);
    double warm_seconds=seconds(mach_absolute_time()-warm_start);
    int error=0;const char *reason=NULL;struct rusage_info_v6 final={0};struct rusage waited={0};int status=0;
    struct sample pre_a={0},pre_b={0};double pre_background=0;
    if (offset!=before.st_size || resident_before==UINT64_MAX || stopped || getppid()!=owner) { error=11;reason="conditioning_failed";goto finish; }
    if (!cache_locked) { reason="cache_lock_unavailable";goto finish; }
    if (!images_prepared) { reason="image_cache_lock_unavailable";goto finish; }
    if ((double)resident_before/pages<.9999) { reason="cache_not_resident";goto finish; }
    for (int i=0;i<load_count;i++) {
        load_pid[i]=fork();
        if (load_pid[i]==0) {
            char parent[32],path[4096];snprintf(parent,sizeof(parent),"%d",getppid());snprintf(path,sizeof(path),"%s.load%d.json",argv[1],i);
            execl(argv[4],argv[4],"50","1150",parent,path,(char *)NULL);_exit(127);
        }
        if (load_pid[i]<0) { error=12;reason="load_launch_failed";goto finish; }
    }
    pause_ms(250);
    if (snapshot(&pre_a,0)) { error=13;reason="preflight_counter_failed";goto finish; }
    pause_ms(1000);
    if (snapshot(&pre_b,0)) { error=13;reason="preflight_counter_failed";goto finish; }
    pre_background=background(&pre_a,&pre_b,0);
    if (max_background>=0 && pre_background>max_background) { reason="background_admission";goto finish; }
    int queue=kqueue();if (queue<0) { error=14;reason="event_queue_failed";goto finish; }
    struct kevent change,event;EV_SET(&change,SIGCHLD,EVFILT_SIGNAL,EV_ADD|EV_ENABLE,0,0,NULL);
    sigset_t blocked,old_mask;sigemptyset(&blocked);sigaddset(&blocked,SIGCHLD);sigprocmask(SIG_BLOCK,&blocked,&old_mask);
    if (kevent(queue,&change,1,NULL,0,NULL)<0) { close(queue);error=15;reason="signal_event_failed";goto finish; }
    if (snapshot(&samples[0],0)) { close(queue);error=16;reason="initial_counter_failed";goto finish; }nsamples=1;
    posix_spawnattr_t attributes;posix_spawnattr_init(&attributes);
    posix_spawnattr_setsigmask(&attributes,&old_mask);posix_spawnattr_setflags(&attributes,POSIX_SPAWN_SETSIGMASK);
    int launched=posix_spawn(&media,argv[8],NULL,&attributes,argv+8,environ);posix_spawnattr_destroy(&attributes);
    if (launched) { media=-1;close(queue);error=17;reason="media_launch_failed";goto finish; }
    while (!stopped && getppid()==owner && seconds(mach_absolute_time()-samples[0].at)<1100) {
        struct timespec timeout={0,250000000};int got=kevent(queue,NULL,0,&event,1,&timeout);
        if (got<0 && errno!=EINTR) { error=18;reason="event_wait_failed";break; }
        siginfo_t ended={0};
        if (waitid(P_PID,(id_t)media,&ended,WEXITED|WNOHANG|WNOWAIT)) { error=19;reason="wait_status_failed";break; }
        if (nsamples>=MAX_SAMPLES || snapshot(&samples[nsamples],1)) { error=20;reason="live_counter_failed";break; }nsamples++;
        if (ended.si_pid==media) {
            if (usage(media,&final) || !final.ri_proc_exit_abstime || !final.ri_proc_start_abstime) { error=21;reason="final_counter_failed";break; }
            if (wait4(media,&status,0,&waited)!=media) { error=22;reason="reap_failed";break; }
            media=-1;break;
        }
    }
    close(queue);sigprocmask(SIG_SETMASK,&old_mask,NULL);
    if (media>0 && !reason) { error=23;reason=stopped?"cancelled":"deadline_or_owner_loss"; }
    if (!reason && (!WIFEXITED(status) || WEXITSTATUS(status))) { error=24;reason="command_failed"; }
finish:
    ;uint64_t resident_after=residency(mapping,size,page);
    int source_unchanged=!fstat(source,&after) && before.st_dev==after.st_dev && before.st_ino==after.st_ino &&
        before.st_size==after.st_size && before.st_mtimespec.tv_sec==after.st_mtimespec.tv_sec && before.st_mtimespec.tv_nsec==after.st_mtimespec.tv_nsec;
    fprintf(report,"{\"status\":\"%s\",\"reason\":\"%s\",\"exit_status\":%d,\"pre_background_cores\":%.9f,\"input_bytes\":%zu,\"page_size\":%ld,\"pages\":%zu,\"resident_before\":%llu,\"resident_after\":%llu,\"source_unchanged\":%s,\"warm_seconds\":%.9f,\"warm_disk_bytes\":%llu,\"touch_checksum\":%llu,\"mach_numer\":%u,\"mach_denom\":%u,\"clock_ticks\":%ld,\"logical_cpus\":%ld,",
        error?"failed":reason?"environment_rejected":"completed",reason?reason:"",status,pre_background,size,page,pages,
        (unsigned long long)resident_before,(unsigned long long)resident_after,source_unchanged?"true":"false",warm_seconds,
        (unsigned long long)(warm_after.ri_diskio_bytesread-warm_before.ri_diskio_bytesread),(unsigned long long)touch,timebase.numer,timebase.denom,sysconf(_SC_CLK_TCK),sysconf(_SC_NPROCESSORS_ONLN));
    fprintf(report,"\"cache_locked\":%s,\"cache_lock_errno\":%d,\"max_background_cores\":%.6f,\"conditioner_wired_bytes\":%llu,",cache_locked?"true":"false",lock_error,max_background,(unsigned long long)warm_after.ri_wired_size);
    fprintf(report,"\"cpu_backend\":\"host_processor_info\",\"images_locked\":%s,\"image_count\":%u,\"image_bytes\":%zu,",images_resident(page)?"true":"false",image_count,image_bytes);
    fprintf(report,"\"process\":{\"wall_seconds\":%.9f,\"user_mach\":%llu,\"system_mach\":%llu,\"child_user_raw\":%llu,\"child_system_raw\":%llu,\"instructions\":%llu,\"cycles\":%llu,\"p_instructions\":%llu,\"p_user_mach\":%llu,\"p_system_mach\":%llu,\"runnable_mach\":%llu,\"disk_read_bytes\":%llu,\"page_wait_mach\":%llu,\"peak_footprint\":%llu,\"wait4_cpu_seconds\":%.9f},\"samples\":[",
        final.ri_proc_exit_abstime?seconds(final.ri_proc_exit_abstime-final.ri_proc_start_abstime):0,
        (unsigned long long)final.ri_user_time,(unsigned long long)final.ri_system_time,(unsigned long long)final.ri_child_user_time,(unsigned long long)final.ri_child_system_time,
        (unsigned long long)final.ri_instructions,(unsigned long long)final.ri_cycles,(unsigned long long)final.ri_pinstructions,
        (unsigned long long)final.ri_user_ptime,(unsigned long long)final.ri_system_ptime,(unsigned long long)final.ri_runnable_time,
        (unsigned long long)final.ri_diskio_bytesread,(unsigned long long)final.ri_page_wait_time_mach,(unsigned long long)final.ri_lifetime_max_phys_footprint,
        waited.ru_utime.tv_sec+waited.ru_utime.tv_usec/1e6+waited.ru_stime.tv_sec+waited.ru_stime.tv_usec/1e6);
    for (unsigned i=0;i<nsamples;i++) {
        struct sample *s=&samples[i];fprintf(report,"%s{\"seconds\":%.9f,\"ticks\":[%llu,%llu,%llu,%llu],\"cpu_mach\":%llu,\"child_cpu_raw\":%llu,\"load_cpu_mach\":%llu,\"monitor_cpu_mach\":%llu}",i?",":"",seconds(s->at-samples[0].at),
            (unsigned long long)s->ticks[0],(unsigned long long)s->ticks[1],(unsigned long long)s->ticks[2],(unsigned long long)s->ticks[3],
            (unsigned long long)s->cpu,(unsigned long long)s->child_cpu,(unsigned long long)s->loads,(unsigned long long)s->monitor);
    }
    fputs("]}\n",report);fclose(report);if (cache_locked) munlock(mapping,size);munmap(mapping,size);close(source);
    for (unsigned i=0;i<image_count;i++) { munlock(images[i].mapping,images[i].size);munmap(images[i].mapping,images[i].size);close(images[i].fd); }
    terminate_owned();mach_port_deallocate(mach_task_self(),host);
    return error?error:0;
}
