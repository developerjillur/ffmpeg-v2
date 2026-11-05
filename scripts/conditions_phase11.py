"""Environment-only validity rules; slow timings are never exclusion criteria."""
from __future__ import annotations
import statistics

DEFAULT_POLICY={'background_admission_max':14.5,'background_block_span_max':.75,
    'background_within_run_iqr_max':1.0,'p_instruction_fraction_block_span_max':.03,
    'synthetic_cpu_block_span_max':.15,'synthetic_cpu_min':.50,'synthetic_cpu_max':1.05,
    'resident_fraction_min':.9999,'direct_disk_bytes_max':8*1024**2,'capture_delay_max':.05,
    'cpu_capacity_error_max':.5,'background_during_run_max':14.5,
    'delivered_cpu_relative_block_span_max':.10}


def percentile(values,fraction):
    ordered=sorted(values);index=(len(ordered)-1)*fraction;low=int(index);high=min(low+1,len(ordered)-1)
    return ordered[low]+(ordered[high]-ordered[low])*(index-low)


def environment(data,*,pipeline=False):
    if data['status']!='completed':return {'valid':False,'reasons':[data.get('reason','not_completed')]}
    scale=data['mach_numer']/data['mach_denom']/1e9;samples=data['samples'];first,last=samples[0],samples[-1]
    wall=last['seconds'];clock=data['clock_ticks'];process=data['process']
    def busy(a,b):return sum((b['ticks'][i]-a['ticks'][i])&0xffffffff for i in (0,1,3))/clock
    loads=(last['load_cpu_mach']-first['load_cpu_mach'])*scale
    monitor=(last['monitor_cpu_mach']-first['monitor_cpu_mach'])*scale
    inclusive=(process['user_mach']+process['system_mach']+process['child_user_raw']+process['child_system_raw'])*scale
    residual=(busy(first,last)-process['wait4_cpu_seconds']-loads-monitor)/wall
    capacity=sum((b-a)&0xffffffff for a,b in zip(first['ticks'],last['ticks']))/clock/wall
    background=[];previous=first
    if not pipeline:
        for current in samples[1:]:
            interval=current['seconds']-previous['seconds']
            if interval<.75:continue
            own=((current['cpu_mach']-previous['cpu_mach'])+(current['load_cpu_mach']-previous['load_cpu_mach'])+
                 (current['monitor_cpu_mach']-previous['monitor_cpu_mach']))*scale
            background.append((busy(previous,current)-own)/interval);previous=current
    iqr=percentile(background,.75)-percentile(background,.25) if len(background)>=2 else 0
    return {'valid':True,'reasons':[],'background_cores':residual,'background_iqr_cores':iqr,
        'cpu_capacity_cores':capacity,'cpu_capacity_error':abs(capacity-data['logical_cpus']),
        'synthetic_cpu_cores':loads/wall,'p_instruction_fraction':process['p_instructions']/process['instructions'] if process['instructions'] else 0,
        'resident_before_fraction':data['resident_before']/data['pages'],'resident_after_fraction':data['resident_after']/data['pages'],
        'disk_read_bytes':process['disk_read_bytes'],'source_unchanged':data['source_unchanged'],
        'capture_delay_seconds':wall-process['wall_seconds'],'inclusive_cpu_error_seconds':abs(inclusive-process['wait4_cpu_seconds']),
        'wait4_cpu_seconds':process['wait4_cpu_seconds'],'delivered_cpu_cores':process['wait4_cpu_seconds']/wall,
        'pre_background_cores':data['pre_background_cores'],
        'observed_background_windows':background,'pipeline':pipeline}


def validate_case(data,load,policy=DEFAULT_POLICY,*,pipeline=False):
    result=environment(data,pipeline=pipeline)
    if not result['valid']:return result
    reasons=result['reasons']
    if not data.get('cache_locked'):reasons.append('input_cache_not_locked')
    if data.get('cpu_backend')!='host_processor_info':reasons.append('cpu_counter_backend')
    if not data.get('images_locked'):reasons.append('image_cache_not_locked')
    if data.get('max_background_cores')!=policy['background_admission_max']:reasons.append('cpu_admission_policy_mismatch')
    if result['cpu_capacity_error']>policy['cpu_capacity_error_max']:reasons.append('cpu_counter_capacity')
    if not -.15<=result['pre_background_cores']<=policy['background_admission_max']:reasons.append('background_admission')
    if not -.15<=result['background_cores']<=policy['background_during_run_max']:reasons.append('background_during_run')
    if not result['source_unchanged']:reasons.append('input_changed')
    for key in ('resident_before_fraction','resident_after_fraction'):
        if not policy['resident_fraction_min']<=result[key]<=1:reasons.append('input_cache_residency')
    if not pipeline and result['disk_read_bytes']>policy['direct_disk_bytes_max']:reasons.append('physical_read_budget')
    if not pipeline and result['background_iqr_cores']>policy['background_within_run_iqr_max']:reasons.append('background_within_run')
    if result['capture_delay_seconds']>policy['capture_delay_max']:reasons.append('counter_capture_delay')
    if result['inclusive_cpu_error_seconds']>max(.005,.001*result['wait4_cpu_seconds']):reasons.append('cpu_accounting')
    if load and not policy['synthetic_cpu_min']<=result['synthetic_cpu_cores']<=policy['synthetic_cpu_max']:reasons.append('synthetic_cpu_duty')
    if not load and result['synthetic_cpu_cores']!=0:reasons.append('unexpected_synthetic_load')
    result['valid']=not reasons;return result


def validate_block(rows,labels,load,policy=DEFAULT_POLICY,*,pipeline=False):
    reasons=[]
    if len(rows)!=2*len(labels) or any(sum(r['label']==label for r in rows)!=2 for label in labels):reasons.append('incomplete_palindrome')
    if any(not r['environment']['valid'] for r in rows):reasons.append('invalid_case_environment')
    if reasons:return {'valid':False,'reasons':reasons}
    metrics={'background_cores':policy['background_block_span_max']}
    if not pipeline:metrics['p_instruction_fraction']=policy['p_instruction_fraction_block_span_max']
    if load:metrics['synthetic_cpu_cores']=policy['synthetic_cpu_block_span_max']
    spans={key:max(r['environment'][key] for r in rows)-min(r['environment'][key] for r in rows) for key in metrics}
    for key,limit in metrics.items():
        if spans[key]>limit:reasons.append(key+'_block_span')
    delivered=[r['environment']['delivered_cpu_cores'] for r in rows]
    relative=(max(delivered)-min(delivered))/statistics.mean(delivered) if min(delivered)>0 else float('inf')
    spans['delivered_cpu_relative']=relative
    if relative>policy['delivered_cpu_relative_block_span_max']:reasons.append('delivered_cpu_relative_block_span')
    return {'valid':not reasons,'reasons':reasons,'spans':spans}
