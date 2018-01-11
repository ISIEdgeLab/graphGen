'''
    Testing functionality for graphGen
'''
import sys
import os
import logging
from subprocess import Popen

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)

INPUT_DIR = 'inputs'
OUTPUT_DIR = 'outputs'
EXE_DIR = '../graphgen'
CWD_DIR = '.'
NETWORK_INPUTS = os.listdir(INPUT_DIR)

def test_basic_command(network_input):
    '''
        run the most basic graphgen -n and -o command to verify outputs
    '''
    cmd = 'python {exe}/graphGen.py -n ' \
        '{cwd}/{out_d}/{no}_temp.ns -o {cwd}/{out_d}/{no}_temp.out ' \
        '{cwd}/{in_d}/{ni}'.format(
            cwd=CWD_DIR,
            exe=EXE_DIR,
            in_d=INPUT_DIR,
            out_d=OUTPUT_DIR,
            ni=network_input,
            no=network_input.split('.')[0],
        )
    LOG.info(cmd)
    # generate outputs to compare with
    generate_p = Popen(cmd, shell=True)
    generate_p_data = generate_p.communicate()
    LOG.info(generate_p_data[0])
    generate_p_rc = generate_p.returncode
    # diff the ns files
    cmd = 'diff -I "^//*" -I "^#*" {out}/{name}_temp.ns {out}/{name}.ns'.format(
        out=OUTPUT_DIR,
        name=network_input.split('.')[0],
    )
    LOG.info(cmd)
    diff_ns_p = Popen(cmd, shell=True)
    diff_ns_p_data = diff_ns_p.communicate()
    LOG.info(diff_ns_p_data[0])
    diff_ns_p_rc = diff_ns_p.returncode
    # diff the vrouter.template files
    cmd = 'diff -I "^//*" -I "^#*" {out}/{name}_temp.out {out}/{name}.out'.format(
        out=OUTPUT_DIR,
        name=network_input.split('.')[0],
    )
    LOG.info(cmd)
    diff_template_p = Popen(cmd, shell=True)
    diff_template_p_data = diff_template_p.communicate()
    LOG.info(diff_template_p_data[0])
    diff_template_p_rc = diff_template_p.returncode

    sys.exit(generate_p_rc+diff_ns_p_rc+diff_template_p_rc)

for net_input in NETWORK_INPUTS:
    test_basic_command(net_input)
