#!/usr/bin/env python
"""
script to monitor HTCondor batch jobs
"""
from __future__ import print_function
import argparse
import os
import math
import glob

# from JMETriggerAnalysis.NTuplizers.utils.common import *
from RecoBTag.PerformanceMeasurements.utils.common import *

def monitor(options, log=''):

    # input directories
    INPUT_DIRS = []

    for i_opt in options.inputs:

        if not os.path.isdir(i_opt):
           if options.verbose: WARNING(log+'input argument is not a valid directory: '+i_opt)
           continue

        INPUT_DIRS += [i_opt]

    INPUT_DIRS = list(set(INPUT_DIRS))

    if len(INPUT_DIRS) == 0:
       return True

    # batch system
    BATCH_RESUB_EXE = 'condor_submit'

    if which(BATCH_RESUB_EXE, permissive=True) is None:
       return False

    ADD_OPTIONS = []

    if options.runtime is not None:
       ADD_OPTIONS += ['-append "+RequestRuntime = '+str(options.runtime)+'"']

    if options.memory is not None:
       ADD_OPTIONS += ['-append "RequestMemory = '+str(options.memory)+'"']

    if len(ADD_OPTIONS) > 0:
       print(' > additional options to "'+BATCH_RESUB_EXE+'":', str(ADD_OPTIONS))

    counter_input = 0
    counter_resubmitted = 0
    counter_toResubmit = 0
    counter_running = 0
    counter_completed = 0

    FILES_INPUT = []

    INPUT_DIRS_2 = []
    for input_dir in INPUT_DIRS:
        for path, subdirs, files in os.walk(input_dir):
            for name in files:
                if os.path.basename(name) == 'condor.sub':
                   INPUT_DIRS_2 += [os.path.dirname(os.path.join(path, name))]

    if len(INPUT_DIRS_2) == 0:
       return True

    INPUT_DIRS_2 = sorted(set(INPUT_DIRS_2))

    condor_subfiles = []
    local_exefiles = []
    running_exes = []
    read_running_exes = True

    for inp_dir in INPUT_DIRS_2:

        job_dirs = glob.glob(inp_dir+'/'+options.jobdirname+'_*/')
        counter_input += len(job_dirs)

        if (options.proxy is not None) and (len(job_dirs) > 0):
           EXE('cp '+str(options.proxy)+' '+inp_dir+'/X509_USER_PROXY', verbose=options.verbose, dry_run=options.dry_run)

        dirs_undone = []
        for _tmp in job_dirs:

            if os.path.isfile(_tmp+'/flag.done'):
               counter_completed += 1
               for _tmp2 in [_tmp+'/flag.queue', _tmp+'/flag.submitted']:
                   if os.path.isfile(_tmp2):
                      EXE('rm -f '+_tmp2, verbose=options.verbose, dry_run=options.dry_run)

            elif os.path.isfile(_tmp+'/flag.queue') or os.path.isfile(_tmp+'/flag.submitted'):
               dirs_undone += [os.path.abspath(_tmp)]

        for _tmp_dirname in dirs_undone:

            if read_running_exes:
               running_exes = HTCondor_jobExecutables_2(os.environ['USER'])
               read_running_exes = False

            if _tmp_dirname+'/exe.sh' in running_exes:
               counter_running += 1
               if os.path.isfile(_tmp_dirname+'/flag.queue'):
                  EXE('mv '+_tmp_dirname+'/flag.queue '+_tmp_dirname+'/flag.submitted', verbose=options.verbose, dry_run=options.dry_run)
            elif options.local:
               counter_completed += 1
               local_exefiles = [_tmp_dirname+'/exe.sh']
               for _tmp2 in [_tmp_dirname+'/flag.queue', _tmp_dirname+'/flag.submitted']:
                   if os.path.isfile(_tmp2):
                      EXE('rm -f '+_tmp2, verbose=options.verbose, dry_run=options.dry_run)
            else:
               resubmit_job = options.resubmit and ((options.max_jobs < 0) or (counter_resubmitted < options.max_jobs))

               if os.path.isfile(_tmp_dirname+'/flag.submitted'):
                  EXE('mv '+_tmp_dirname+'/flag.submitted '+_tmp_dirname+'/flag.queue', verbose=options.verbose, dry_run=options.dry_run)

               if resubmit_job:
                  counter_resubmitted += 1
                  condor_subfiles += [_tmp_dirname+'/../condor.sub']
               else:
                  counter_toResubmit += 1

    if options.local:
       local_exefiles = sorted(set([os.path.abspath(_tmp) for _tmp in local_exefiles]))
       for _tmp in local_exefiles:
           EXE(_tmp, verbose=options.verbose, dry_run=options.dry_run)
    else:
       condor_subfiles = sorted(set([os.path.abspath(_tmp) for _tmp in condor_subfiles]))
       condor_submit_optstr = (' '+(' '.join(ADD_OPTIONS)) if (len(ADD_OPTIONS) > 0) else '')
       for _tmp in condor_subfiles:
           EXE(BATCH_RESUB_EXE+' '+_tmp+condor_submit_optstr, verbose=options.verbose, dry_run=options.dry_run)

    counter_format = '{:>'+str(1+int(math.log10(counter_input)))+'}' if counter_input > 0 else '{:>1}'

    print('')
    print('-'*51)
    print('')
    print(' Number of input  files found : '+colored_text(counter_format.format(counter_input), ['1']))
    print(' Number of output files found : '+colored_text(counter_format.format(counter_completed), ['1', '92']))
    print(' Number of resubmitted jobs   : '+colored_text(counter_format.format(counter_resubmitted), ['1', '94']))
    print(' Number of jobs to resubmit   : '+colored_text(counter_format.format(counter_toResubmit), ['1', '94']))
    print('')
    print(' Number of jobs still running : '+counter_format.format(counter_running))
    print('')
    print('-'*51)
    print('')

    return bool(counter_input == counter_completed)

#### main
if __name__ == '__main__':
    ### args
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument('-i', '--inputs', dest='inputs', nargs='+', default=[], required=True,
                        help='list of paths to input directories')

    parser.add_argument('--skip', dest='skip', nargs='+', default=[],
                        help='list of job-ID numbers to be ignored')

    parser.add_argument('-r', '--resubmit', dest='resubmit', action='store_true', default=False,
                        help='enable resubmission of batch jobs')

    parser.add_argument('-j', '--jobdirname', dest='jobdirname', action='store', default='job', required=False,
                        help='prefix of batch-job sub-directories (example: [JOBDIRNAME]_[counter]/)')

    parser.add_argument('-p', '--proxy', dest='proxy', action='store', default=None, required=False,
                        help='path to voms proxy (if specified, will overwrite the file X509_USER_PROXY in every valid submission directory)')

    parser.add_argument('--memory', dest='memory', action='store', type=int, default=None, required=False,
                        help='argument of HTCondor parameter "RequestMemory"')

    parser.add_argument('--runtime', dest='runtime', action='store', type=int, default=None, required=False,
                        help='argument of HTCondor parameter "+RequestRuntime"')

    parser.add_argument('-m', '--max-jobs', dest='max_jobs', action='store', type=int, default=-1,
                        help='maximum number of jobs that can submitted to the batch system')

    parser.add_argument('--repeat', dest='repeat', nargs='?', type=int, const=-1, default=None,
                        help='number of times the monitoring is repeated (enables continuous monitoring; see -f for monitoring frequency); if value is not specified or negative, monitoring stops only when all jobs are completed')

    parser.add_argument('-f', '--frequency', dest='frequency', action='store', type=int, default=3600,
                        help='interval of time in seconds between executions of the monitor (has no effect if --repeat is not specified)')

    parser.add_argument('-l', '--local', dest='local', action='store_true', default=False,
                        help='execute jobs locally')

    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False,
                        help='enable verbose mode')

    parser.add_argument('-d', '--dry-run', dest='dry_run', action='store_true', default=False,
                        help='enable dry-run mode')

    opts, opts_unknown = parser.parse_known_args()
    ### ----

    log_prx = os.path.basename(__file__)+' -- '

    if (opts.memory is not None) and (opts.memory <= 0):
       KILL(log_prx+'invalid (non-positive) value for HTCondor parameter "RequestMemory": '+str(opts.memory))

    if (opts.runtime is not None) and (opts.runtime <= 0):
       KILL(log_prx+'invalid (non-positive) value for HTCondor parameter "+RequestRuntime": '+str(opts.runtime))

    if (opts.proxy is not None) and (not os.path.isfile(opts.proxy)):
       KILL(log_prx+'invalid path to voms proxy: '+str(opts.proxy))

    if len(opts_unknown) > 0:
       KILL(log_prx+'unsupported command-line arguments: '+str(opts_unknown))

    if opts.repeat != 0:

       if opts.repeat is not None:

          n_reps = 0

          SLEEP_CMD = 'sleep '+str(opts.frequency)

       while not monitor(options=opts, log=log_prx):

          if opts.repeat is None: break

          n_reps += 1

          if (opts.repeat >= 0) and (n_reps == opts.repeat): break

          EXE(SLEEP_CMD, verbose=opts.verbose, dry_run=opts.dry_run)
