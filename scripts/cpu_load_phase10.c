/* One bounded duty-cycled diagnostic worker; no changes to other processes. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <libproc.h>
#include <sys/resource.h>
#include <mach/mach_time.h>

static volatile sig_atomic_t stop;
static void stopped(int number) { (void)number;stop=1; }
static uint64_t ns(void) { return clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW); }

int main(int argc,char **argv) {
    if (argc!=5) return 2;
    int duty=atoi(argv[1]),seconds=atoi(argv[2]);pid_t owner=(pid_t)atoi(argv[3]);
    if (duty<0 || duty>100 || seconds<1 || seconds>1200 || owner<2 || getppid()!=owner) return 3;
    int fd=open(argv[4],O_WRONLY|O_CREAT|O_EXCL,0600);if (fd<0) return 4;
    signal(SIGTERM,stopped);signal(SIGINT,stopped);
    struct rusage_info_v6 before={0},after={0};
    int supported=proc_pid_rusage(getpid(),RUSAGE_INFO_V6,(rusage_info_t *)&before)==0;
    uint64_t start=ns(),cpu_start=clock_gettime_nsec_np(CLOCK_THREAD_CPUTIME_ID),iterations=0,value=2026110410;
    const uint64_t period=50000000,active=period*duty/100;
    while (!stop && getppid()==owner && ns()-start<(uint64_t)seconds*1000000000) {
        uint64_t cycle=ns();
        while (!stop && ns()-cycle<active) {
            for (unsigned i=0;i<8192;i++) { value^=value<<13;value^=value>>7;value^=value<<17; }
            iterations+=8192;
        }
        uint64_t end=ns();
        if (end-cycle<period) { uint64_t remaining=period-(end-cycle);struct timespec pause={remaining/1000000000,remaining%1000000000};nanosleep(&pause,NULL); }
    }
    int ok=supported && proc_pid_rusage(getpid(),RUSAGE_INFO_V6,(rusage_info_t *)&after)==0;
    mach_timebase_info_data_t scale;mach_timebase_info(&scale);
    dprintf(fd,"{\"pid\":%d,\"owner\":%d,\"duty\":%d,\"wall_ns\":%llu,\"cpu_ns\":%llu,\"iterations\":%llu,\"checksum\":%llu,\"rusage_v6\":%s,\"user_mach\":%llu,\"system_mach\":%llu,\"p_user_mach\":%llu,\"p_system_mach\":%llu,\"instructions\":%llu,\"p_instructions\":%llu,\"runnable_raw\":%llu,\"mach_numer\":%u,\"mach_denom\":%u}\n",
            getpid(),owner,duty,(unsigned long long)(ns()-start),(unsigned long long)(clock_gettime_nsec_np(CLOCK_THREAD_CPUTIME_ID)-cpu_start),
            (unsigned long long)iterations,(unsigned long long)value,ok?"true":"false",
            (unsigned long long)(after.ri_user_time-before.ri_user_time),(unsigned long long)(after.ri_system_time-before.ri_system_time),
            (unsigned long long)(after.ri_user_ptime-before.ri_user_ptime),(unsigned long long)(after.ri_system_ptime-before.ri_system_ptime),
            (unsigned long long)(after.ri_instructions-before.ri_instructions),(unsigned long long)(after.ri_pinstructions-before.ri_pinstructions),
            (unsigned long long)(after.ri_runnable_time-before.ri_runnable_time),scale.numer,scale.denom);
    close(fd);return ok?0:5;
}
