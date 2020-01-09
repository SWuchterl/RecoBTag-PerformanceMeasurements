#!/usr/bin/env python
"""
script to create area for submission of HTCondor batch jobs
"""
from __future__ import print_function
import argparse
import os
import sys
import math
import json
import datetime

# from JMETriggerAnalysis.NTuplizers.utils.common import *
# from JMETriggerAnalysis.NTuplizers.utils.das import load_dataset_data, skim_das_jsondump
from RecoBTag.PerformanceMeasurements.utils.common import *
from RecoBTag.PerformanceMeasurements.utils.das import load_dataset_data, skim_das_jsondump

#### main
if __name__ == '__main__':
    ### args
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument('-c', '--cfg', dest='cmsRun_cfg', action='store', default=None, required=True,
                        help='path to cmsRun cfg file')

    parser.add_argument('--customize-cfg', dest='customize_cfg', action='store_true', default=False,
                        help='append minimal customization to cmsRun-cfg required by the driver')

    parser.add_argument('-d', '--dataset', dest='dataset', action='store', default=None, required=True,
                        help='name of input data set in DAS')

    parser.add_argument('-o', '--output', dest='output', action='store', default=None, required=True,
                        help='path to output directory')

    parser.add_argument('-j', '--jobdirname', dest='jobdirname', action='store', default='job', required=False,
                        help='prefix of batch-job sub-directories (example: [JOBDIRNAME]_[counter]/)')

    parser.add_argument('-f', '--max-files', dest='max_files', action='store', type=int, default=-1, required=False,
                        help='maximum number of input files to be processed (if integer is negative, all files will be processed)')

    parser.add_argument('-m', '--max-events', dest='max_events', action='store', type=int, default=-1, required=False,
                        help='maximum number of total input events to be processed (if integer is negative, all events will be processed)')

    parser.add_argument('-n', '--n-events', dest='n_events', action='store', type=int, default=-1, required=False,
                        help='maximum number of events per job')

    parser.add_argument('-p', '--parentFiles-level', dest='parentFiles_level', action='store', type=int, default=2, required=False,
                        help='level of parentFiles to be used as secondary input files (currently, anything other than 1 and 2 disables the usage of secondary input files)')

    parser.add_argument('--cpus', dest='cpus', action='store', type=int, default=1, required=False,
                        help='argument of HTCondor parameter "RequestCpus"')

    parser.add_argument('--memory', dest='memory', action='store', type=int, default=2000, required=False,
                        help='argument of HTCondor parameter "RequestMemory"')

    parser.add_argument('--runtime', dest='runtime', action='store', type=int, default=10800, required=False,
                        help='argument of HTCondor parameter "+RequestRuntime"')

    parser.add_argument('--batch-name', dest='batch_name', action='store', default=None, required=False,
                        help='argument of HTCondor parameter "batch_name" (if not specified, basename of argument of "--output" is used)')

    parser.add_argument('--submit', dest='submit', action='store_true', default=False,
                        help='submit job(s) on the batch system')

    parser.add_argument('--no-export-LD-LIBRARY-PATH', dest='no_export_LD_LIBRARY_PATH', action='store_true', default=False,
                        help='do not export explicitly the environment variable "LD_LIBRARY_PATH" in the batch-job executable')

    parser.add_argument('--dry-run', dest='dry_run', action='store_true', default=False,
                        help='enable dry-run mode')

    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', default=False,
                        help='enable verbose mode')

    opts, opts_unknown = parser.parse_known_args()
    ### -------------------------

    log_prx = os.path.basename(__file__)+' -- '

    ### opts --------------------
    if 'CMSSW_BASE' not in os.environ:
       KILL(log_prx+'global variable CMSSW_BASE is not defined (set up CMSSW environment with "cmsenv" before submitting jobs)')

    if not os.path.isfile(opts.cmsRun_cfg):
       KILL(log_prx+'invalid path to cmsRun cfg file [-c]: '+str(opts.cmsRun_cfg))

    if os.path.exists(opts.output):
       KILL(log_prx+'target path to output directory already exists [-o]: '+str(opts.output))

    OUTPUT_DIR = os.path.abspath(opts.output)

    if opts.n_events == 0:
       KILL(log_prx+'logic error: requesting zero events per job (use non-zero value for argument of option "-n")')

    if opts.submit and (not opts.dry_run):
       which('condor_submit')

    if opts.cpus <= 0:
       KILL(log_prx+'invalid (non-positive) value for HTCondor parameter "RequestCpus": '+str(opts.cpus))

    if opts.memory <= 0:
       KILL(log_prx+'invalid (non-positive) value for HTCondor parameter "RequestMemory": '+str(opts.memory))

    if opts.runtime <= 0:
       KILL(log_prx+'invalid (non-positive) value for HTCondor parameter "+RequestRuntime": '+str(opts.runtime))

    is_slc7_arch = False
    if os.environ['SCRAM_ARCH'].startswith('slc7'): is_slc7_arch = True
    elif os.environ['SCRAM_ARCH'].startswith('slc6'): pass
    else:
       KILL(log_prc+'could not infer architecture from environment variable "SCRAM_ARCH": '+str(os.environ['SCRAM_ARCH']))

    if opts.max_events == 0:
       KILL(log_prx+'logic error: requesting a maximum of zero input events (use non-zero value for argument of option --max-events/-m)')

    if opts.max_files == 0:
       KILL(log_prx+'logic error: requesting a maximum of zero input files (use non-zero value for argument of option --max-files/-f)')

    ### unrecognized command-line arguments
    ### -> used as additional command-line arguments to cmsRun
    if opts.verbose and len(opts_unknown):
       print('-'*50)
       print(colored_text('additional cmsRun command-line arguments:', ['1']))
       for _tmp in opts_unknown: print(' '+str(_tmp))
       print('-'*50)

    ### extract input-files information from data set name via dasgoclient
    ### -> list of dictionaries, each containing DAS name, files, number of events per file, and parent files
    input_dset = {}

    if os.path.isfile(opts.dataset):
       input_dset = skim_das_jsondump(file_path=opts.dataset, max_files=opts.max_files, max_events=opts.max_events, verbose=opts.verbose)
    else:
       which('dasgoclient')
       input_dset = load_dataset_data(das_name=opts.dataset, max_files=opts.max_files, max_events=opts.max_events, verbose=opts.verbose)

    ### total number of events and jobs
    ### -> used to determine format of output-file name
    nJobs, totEvents, breakLoop = 0, 0, False
    for i_inpfdc in input_dset['files']:
        i_nevents = i_inpfdc['nevents']
        totEvents += i_nevents
        if (opts.max_events > 0) and (totEvents >= opts.max_events):
           i_nevents -= (totEvents - opts.max_events)
           breakLoop = True
        nJobs += int(math.ceil(float(i_nevents) / opts.n_events)) if (opts.n_events > 0) else 1
        if breakLoop:
           break
    if nJobs == 0:
       KILL(log_prx+'input error: expected number of batch jobs is zero (check input data set and number of events): '+opts.dataset)
    outputname_postfix_format = '_{:0'+str(max(1, int(math.ceil(math.log10(nJobs)))))+'d}'
    del nJobs, totEvents, breakLoop

    ### voms proxy
    voms_proxy_path = None

    if ('X509_USER_PROXY' in os.environ):
       voms_proxy_path = os.environ['X509_USER_PROXY']
    else:
       voms_proxy_path = '/tmp/x509up_u'+str(os.getuid())

    if not os.path.isfile(voms_proxy_path):
       EXE('voms-proxy-init --voms cms', verbose=opts.verbose, dry_run=opts.dry_run)

    if not os.path.isfile(voms_proxy_path):
       KILL(log_prx+'invalid path to voms proxy: '+voms_proxy_path)

    EXE('mkdir -p '+OUTPUT_DIR, verbose=opts.verbose, dry_run=opts.dry_run)
    EXE('cp '+voms_proxy_path+' '+OUTPUT_DIR+'/X509_USER_PROXY', verbose=opts.verbose, dry_run=opts.dry_run)

    ### copy cmsRun-cfg into output directory
    out_cmsRun_cfg = os.path.abspath(OUTPUT_DIR+'/cfg.py')
    EXE('cp '+opts.cmsRun_cfg+' '+out_cmsRun_cfg, verbose=opts.verbose, dry_run=opts.dry_run)

    if opts.customize_cfg:
       with open(out_cmsRun_cfg, 'a') as cfg_file:
            custom_str = """
###
### customization added by {:} [time-stamp: {:}]
###
import FWCore.ParameterSet.VarParsing as vpo
opts = vpo.VarParsing('analysis')
opts.register('skipEvents', 0,
              vpo.VarParsing.multiplicity.singleton,
              vpo.VarParsing.varType.int,
              'number of events to be skipped')
opts.register('dumpPython', None,
              vpo.VarParsing.multiplicity.singleton,
              vpo.VarParsing.varType.string,
              'Path to python file with content of cms.Process')
# max number of events to be processed
process.maxEvents.input = opts.maxEvents
# number of events to be skipped
process.source.skipEvents = cms.untracked.uint32(opts.skipEvents)
# input EDM files [primary]
process.source.fileNames = opts.inputFiles
# input EDM files [secondary]
process.source.secondaryFileNames = opts.secondaryInputFiles
# dump content of cms.Process to python file
if opts.dumpPython is not None:
   open(opts.dumpPython, 'w').write(process.dumpPython())
"""
            cfg_file.write(custom_str.format(os.path.basename(__file__), str(datetime.datetime.now())))

    ### copy driver command
    if not opts.dry_run:
       with open(os.path.abspath(OUTPUT_DIR+'/cmdLog'), 'w') as file_cmdLog:
            file_cmdLog.write((' '.join(sys.argv[:]))+'\n')

    ### copy dataset information in .json format
    if not opts.dry_run:
       json.dump(input_dset, open(OUTPUT_DIR+'/dataset.json', 'w'), sort_keys=True, indent=2)

    ### condor submission file
    SUBFILE_ABSPATH = OUTPUT_DIR+'/condor.sub'

    if os.path.exists(SUBFILE_ABSPATH):
       KILL(log_prx+'target output file already exists (condor submission file): '+SUBFILE_ABSPATH)

    SUBFILE_LINES = [
      'BASEDIR = '+OUTPUT_DIR,
      'batch_name = '+(opts.batch_name if (opts.batch_name is not None) else '$Fn(BASEDIR)'),
      'initialdir = $DIRNAME(QFILE)',
      'executable = $(initialdir)/exe.sh',
      'output = logs/out.$(Cluster).$(Process)',
      'error  = logs/err.$(Cluster).$(Process)',
      'log    = logs/log.$(Cluster).$(Process)',
      '#arguments =',
      '#transfer_executable = True',
      '#transfer_input_files =',
      'universe = vanilla',
      'getenv = True',
      'should_transfer_files = IF_NEEDED',
      'when_to_transfer_output = ON_EXIT',
      'requirements = (OpSysAndVer == "'+('CentOS7' if is_slc7_arch else 'SL6')+'")',
      'RequestCpus = '+str(opts.cpus),
      'RequestMemory = '+str(opts.memory),
      '+RequestRuntime = '+str(opts.runtime),
      'x509userproxy = $(BASEDIR)/X509_USER_PROXY',
      'queue QFILE matching files $(BASEDIR)/*/flag.queue',
    ]

    if not opts.dry_run:
       with open(SUBFILE_ABSPATH, 'w') as f_subfile:
          for _tmp in SUBFILE_LINES:
              f_subfile.write(_tmp+'\n')

    ### create output batch scripts
    jobCounter = 0
    totEvents = 0
    breakLoop = False

    for i_inpfdc in input_dset['files']:

        i_inputFile = i_inpfdc['file']
        i_inputFile_nevents = i_inpfdc['nevents']

        i_secondaryInputFiles = None
        if opts.parentFiles_level == 2:
           i_secondaryInputFiles = i_inpfdc['parentFiles_2']
        elif opts.parentFiles_level == 1:
           i_secondaryInputFiles = i_inpfdc['parentFiles_1']

        # number of jobs for this set of input files
        i_njobs = int(math.ceil(float(i_inputFile_nevents) / opts.n_events)) if (opts.n_events > 0) else 1
        i_nevt_remainder = i_inputFile_nevents%opts.n_events if (opts.n_events > 0) else 0

        for i_job in range(i_njobs):

            # name of output sub-directory
            i_OUTPUT_DIR = OUTPUT_DIR+'/'+opts.jobdirname+outputname_postfix_format.format(jobCounter)

            # create logs/ directory for HTCondor log-files
            EXE('mkdir -p '+str(i_OUTPUT_DIR)+'/logs', verbose=opts.verbose, dry_run=opts.dry_run)

            # create (empty) queue-file to trigger job submission
            EXE('touch '+str(i_OUTPUT_DIR)+'/flag.queue', verbose=opts.verbose, dry_run=opts.dry_run)

            # number of events for this job
            i_maxEvents = opts.n_events if (opts.n_events > 0) else i_inputFile_nevents
            if (i_job == (i_njobs - 1)) and (i_nevt_remainder != 0):
               i_maxEvents = i_nevt_remainder

            totEvents += i_maxEvents
            if (opts.max_events > 0) and (totEvents >= opts.max_events):
               i_maxEvents -= (totEvents - opts.max_events)
               breakLoop = True

            # cmsRun arguments (cfg-file + options)
            cmsRun_opts = out_cmsRun_cfg
            cmsRun_opts += ' \\\n maxEvents='+str(i_maxEvents)
            cmsRun_opts += ' \\\n skipEvents='+str(opts.n_events*i_job)
            cmsRun_opts += ' \\\n inputFiles='+str(i_inputFile)
            if i_secondaryInputFiles is not None:
               cmsRun_opts += ' \\\n secondaryInputFiles='+str(','.join(i_secondaryInputFiles))
            for _tmp in opts_unknown:
                cmsRun_opts += ' \\\n '+str(_tmp)

            ## dump of full python config
            if jobCounter == 0:
               EXE('python '+cmsRun_opts+' dumpPython='+OUTPUT_DIR+'/dumpPython.py &> /dev/null', suspend=False, verbose=opts.verbose, dry_run=opts.dry_run)

            i_SHELL_COMMANDS  = [['set -e']]
            i_SHELL_COMMANDS += [['if [ -f flag.done ]; then exit 0; fi;']]
            i_SHELL_COMMANDS += [['cd '+os.environ['CMSSW_BASE']+'/src']]
            i_SHELL_COMMANDS += [['eval `scram runtime -sh`']]
            i_SHELL_COMMANDS += [['cd -']]
            i_SHELL_COMMANDS += [['cmsRun '+cmsRun_opts]]
            i_SHELL_COMMANDS += [['touch flag.done']]

            EXEFILE_ABSPATH = i_OUTPUT_DIR+'/exe.sh'

            if os.path.exists(EXEFILE_ABSPATH):
               KILL(log_prx+'target output file already exists (executable of batch job): '+EXEFILE_ABSPATH)

            if not opts.dry_run:
               with open(EXEFILE_ABSPATH, 'w') as f_exefile:

                  f_exefile.write('#!/bin/bash\n')

                  # export explicitly the environment variable LD_LIBRARY_PATH
                  if not opts.no_export_LD_LIBRARY_PATH:
                     if 'LD_LIBRARY_PATH' in os.environ:
                        f_exefile.write('\n'+'export LD_LIBRARY_PATH='+os.environ['LD_LIBRARY_PATH']+'\n')

                  f_exefile.write('\n'+('\n\n'.join([' \\\n '.join(_tmp) for _tmp in i_SHELL_COMMANDS]))+'\n')

            print(colored_text('output:', ['1', '94']), os.path.relpath(EXEFILE_ABSPATH, os.environ['PWD']))

            EXE('chmod u+x '+EXEFILE_ABSPATH, verbose=opts.verbose, dry_run=opts.dry_run)

            jobCounter += 1

            if breakLoop:
               break

    del jobCounter, totEvents, breakLoop

    if opts.submit:
       EXE('condor_submit '+SUBFILE_ABSPATH, suspend=False, verbose=opts.verbose, dry_run=opts.dry_run)
