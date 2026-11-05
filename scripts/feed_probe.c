/* Read-only encoder-feed and thread-policy instrumentation for excluded probes. */
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
#include <x264.h>

static int trace_fd = -1;
static atomic_uint pictures;
static uint64_t started_ns, open_ns, first_input_ns, last_return_ns, call_ns, gap_ns;
static unsigned calls, inputs;

static uint64_t now_ns(void) {
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return (uint64_t)value.tv_sec * 1000000000 + (uint64_t)value.tv_nsec;
}

static unsigned int qos(void) {
    int relative = 0;
    qos_class_t value = QOS_CLASS_UNSPECIFIED;
    pthread_get_qos_class_np(pthread_self(), &value, &relative);
    return (unsigned int)value;
}

__attribute__((constructor)) static void begin_trace(void) {
    started_ns = now_ns();
    const char *path = getenv("FFV2_FEED_TRACE");
    if (path) trace_fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_APPEND, 0600);
    if (trace_fd >= 0) dprintf(trace_fd, "{\"event\":\"load\",\"pid\":%d,\"qos\":%u}\n", getpid(), qos());
}

/* The diagnostic corpus has one video encoder; its calls are serialized. */
__attribute__((destructor)) static void end_trace(void) {
    if (trace_fd >= 0)
        dprintf(trace_fd, "{\"event\":\"timing\",\"calls\":%u,\"input_frames\":%u,\"open_seconds\":%.9f,\"first_input_seconds\":%.9f,\"encode_call_seconds\":%.9f,\"between_call_seconds\":%.9f,\"observed_process_seconds\":%.9f}\n",
                calls, inputs, open_ns / 1e9, (first_input_ns ? first_input_ns - started_ns : 0) / 1e9,
                call_ns / 1e9, gap_ns / 1e9, (now_ns() - started_ns) / 1e9);
}

struct entry { void *(*routine)(void *); void *argument; const char *library; };
static void *thread_entry(void *opaque) {
    struct entry value = *(struct entry *)opaque;
    free(opaque);
    int policy = 0;
    struct sched_param parameter = {0};
    pthread_getschedparam(pthread_self(), &policy, &parameter);
    if (trace_fd >= 0) dprintf(trace_fd, "{\"event\":\"thread\",\"library\":\"%s\",\"qos\":%u,\"policy\":%d,\"priority\":%d}\n",
                               value.library ? value.library : "", qos(), policy, parameter.sched_priority);
    return value.routine(value.argument);
}

static int probe_pthread_create(pthread_t *thread, const pthread_attr_t *attribute, void *(*routine)(void *), void *argument) {
    if (trace_fd < 0) return pthread_create(thread, attribute, routine, argument);
    struct entry *value = malloc(sizeof(*value));
    if (!value) return pthread_create(thread, attribute, routine, argument);
    Dl_info info = {0};
    dladdr((const void *)routine, &info);
    *value = (struct entry){routine, argument, info.dli_fname};
    int result = pthread_create(thread, attribute, thread_entry, value);
    if (result) free(value);
    return result;
}

static x264_t *probe_open(x264_param_t *parameter) {
    uint64_t before = now_ns();
    x264_t *encoder = x264_encoder_open(parameter);
    open_ns += now_ns() - before;
    if (encoder && trace_fd >= 0) {
        x264_param_t actual;
        x264_encoder_parameters(encoder, &actual);
        dprintf(trace_fd, "{\"event\":\"open\",\"width\":%d,\"height\":%d,\"threads\":%d,\"lookahead_threads\":%d,\"sync_lookahead\":%d,\"rc_lookahead\":%d,\"sliced\":%d,\"cpu\":%u,\"qos\":%u}\n",
                actual.i_width, actual.i_height, actual.i_threads, actual.i_lookahead_threads,
                actual.i_sync_lookahead, actual.rc.i_lookahead, actual.b_sliced_threads, actual.cpu, qos());
    }
    return encoder;
}

static int probe_encode(x264_t *encoder, x264_nal_t **nals, int *count, x264_picture_t *input, x264_picture_t *output) {
    uint64_t before = now_ns();
    if (last_return_ns) gap_ns += before - last_return_ns;
    if (input) {
        inputs++;
        if (!first_input_ns) first_input_ns = before;
    }
    if (input && trace_fd >= 0 && atomic_fetch_add(&pictures, 1) < 3)
        dprintf(trace_fd, "{\"event\":\"frame\",\"strides\":[%d,%d,%d],\"alignment128\":[%lu,%lu,%lu],\"qos\":%u}\n",
                input->img.i_stride[0], input->img.i_stride[1], input->img.i_stride[2],
                (unsigned long)((uintptr_t)input->img.plane[0] % 128),
                (unsigned long)((uintptr_t)input->img.plane[1] % 128),
                (unsigned long)((uintptr_t)input->img.plane[2] % 128), qos());
    int result = x264_encoder_encode(encoder, nals, count, input, output);
    last_return_ns = now_ns();
    call_ns += last_return_ns - before;
    calls++;
    return result;
}

#define INTERPOSE(replacement, original, name) \
__attribute__((used, section("__DATA,__interpose"))) static const struct { const void *new_function; const void *old_function; } name = {(const void *)(replacement), (const void *)(original)}
INTERPOSE(probe_open, x264_encoder_open, open_pair);
INTERPOSE(probe_encode, x264_encoder_encode, encode_pair);
INTERPOSE(probe_pthread_create, pthread_create, thread_pair);
