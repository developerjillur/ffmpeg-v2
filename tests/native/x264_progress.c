/* Stress the actual patched frame-progress API, including buffer reuse. */
#include "common/common.h"
#include <stdatomic.h>
#include <sched.h>

enum { ROWS=4096, READERS=8, CYCLES=16 };
struct shared {
    x264_frame_t frame;
    uint64_t payload[ROWS];
    unsigned cycle;
    atomic_uint errors;
};
struct reader { struct shared *shared;unsigned index; };

static uint64_t expected(unsigned cycle,unsigned row) {
    return ((uint64_t)(cycle+1)<<32) ^ ((uint64_t)row*UINT64_C(0x9e3779b9));
}
static void *publish(void *opaque) {
    struct shared *state=opaque;
    /* Real frame filters may publish negative padding before the first row. */
    x264_frame_cond_broadcast(&state->frame,-48);
    x264_frame_cond_broadcast(&state->frame,-24);
    x264_frame_cond_broadcast(&state->frame,-8);
    for (unsigned row=0;row<ROWS;row++) {
        state->payload[row]=expected(state->cycle,row);
        x264_frame_cond_broadcast(&state->frame,(int)row);
        if (!(row%31)) sched_yield();
    }
    return NULL;
}
static void *consume(void *opaque) {
    struct reader *reader=opaque;struct shared *state=reader->shared;
    for (unsigned row=0;row<ROWS;row++) {
        int completed;
        if (reader->index%2) completed=x264_frame_cond_wait(&state->frame,(int)row);
        else {
            while ((completed=x264_frame_cond_wait(&state->frame,-1))<(int)row) sched_yield();
        }
        if (completed<(int)row || completed>=ROWS || state->payload[row]!=expected(state->cycle,row))
            atomic_fetch_add(&state->errors,1);
    }
    return NULL;
}
int main(void) {
    struct shared *state=calloc(1,sizeof(*state));if (!state) return 2;
    if (x264_pthread_mutex_init(&state->frame.mutex,NULL) || x264_pthread_cond_init(&state->frame.cv,NULL)) return 3;
    for (unsigned cycle=0;cycle<CYCLES;cycle++) {
        state->cycle=cycle;x264_frame_cond_broadcast(&state->frame,-1);
        if (x264_frame_cond_wait(&state->frame,-1)!=-1) return 4;
        pthread_t writer,readers[READERS];struct reader arguments[READERS];
        for (unsigned i=0;i<READERS;i++) {
            arguments[i]=(struct reader){state,i};
            if (pthread_create(&readers[i],NULL,consume,&arguments[i])) return 5;
        }
        if (pthread_create(&writer,NULL,publish,state)) return 6;
        pthread_join(writer,NULL);
        for (unsigned i=0;i<READERS;i++) pthread_join(readers[i],NULL);
        if (x264_frame_cond_wait(&state->frame,ROWS-1)!=ROWS-1) return 7;
    }
    unsigned errors=atomic_load(&state->errors);
    fprintf(stderr,"{\"cycles\":%u,\"readers\":%u,\"rows\":%u,\"checks\":%u,\"errors\":%u}\n",CYCLES,READERS,ROWS,CYCLES*READERS*ROWS,errors);
    x264_pthread_cond_destroy(&state->frame.cv);x264_pthread_mutex_destroy(&state->frame.mutex);free(state);
    return errors?1:0;
}
