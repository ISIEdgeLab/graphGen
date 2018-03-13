#! /usr/bin/env python

from subprocess import Popen, PIPE, check_call
import socket
import argparse

# changing all the names for a script is cancerous, ignore.
# pylint: disable=invalid-name
parser = argparse.ArgumentParser(description='Configure Enclave routes from enclave.routes')
parser.add_argument('subnet', nargs='?', type=str, default='2', help='Specify the outgoing subnet')
parser.add_argument('--st', '--secondary-table', dest='stable', action='store_const',
                    const=True, default=False,
                    help='Configure a secondary routing table for multihomed enclaves')
args = parser.parse_args()

output, _ = Popen(["ip", "route"], stdout=PIPE, stderr=PIPE).communicate()
out = output.splitlines()

lines_to_remove = []
ifaces = {}

subnet = args.subnet

# pylint: disable=too-many-boolean-expressions
for line in out:
    tokens = line.strip("\n").split()
    if (len(tokens) >= 5 and tokens[1] == "via" and tokens[0] != 'default' and
            (tokens[0] != '192.168.0.0/22' and tokens[0] != '172.16.0.0/12' and
             tokens[0] != '192.168.0.0/16' and tokens[0] != '224.0.0.0/4' and
             tokens[0] != '172.17.0.0/16')):
        lines_to_remove.append(line)
    else:
        if (tokens[0] != 'default' and
                (tokens[0] != '192.168.0.0/22' and tokens[0] != '172.16.0.0/12' and
                 tokens[0] != '192.168.0.0/16' and tokens[0] != '224.0.0.0/4' and
                 tokens[0] != '172.17.0.0/16')):
            quad = tokens[0].split('.')
            if quad[2] == subnet:
                ifaces[quad[1]] = tokens[2]

# clear any rules if we have them:

output, _ = Popen(["ip", "rule"], stdout=PIPE, stderr=PIPE).communicate()
out = output.splitlines()
for line in out:
    tokens = line.strip("\n").split()
    for iface in ifaces:
        if tokens[1] == 'from' and tokens[2] == '10.%s.0.0/16' % iface:
            cmd = 'sudo ip rule del from 10.%s.0.0/16' % iface
            check_call(cmd.split(), stdout=PIPE, stderr=PIPE)

in_routes = open('/tmp/enclave.routes', 'r')
sn = socket.gethostname().split('.')[0]

for line in lines_to_remove:
    route_to_rem = 'sudo ip route del %s' % line
    check_call(route_to_rem.split(), stdout=PIPE, stderr=PIPE)

if not args.stable:
    for line in in_routes:
        tokens = line.strip("\n").split()
        if tokens[0] == sn and tokens[2] != "0":
            route_to_add = 'sudo ip route add 10.%s.0.0/16 via 10.%s.%s.2 dev %s' % (
                tokens[1], tokens[2], subnet, ifaces[tokens[2]]
            )
            check_call(route_to_add.split(), stdout=PIPE, stderr=PIPE)

else:
    # Check to see if a secondary table exists
    with open('/etc/iproute2/rt_tables', 'r') as r_tables:
        second_table_exists = False
        for line in r_tables:
            tokens = line.strip("\n").split()
            if tokens[-1] == 'rt2':
                second_table_exists = True

    if not second_table_exists:
        with open('/etc/iproute2/rt_tables', 'a') as r_tables:
            r_tables.write('1 rt2')

    for iface in ifaces:
        if int(iface) > 50:
            # flush the old table
            cmd = 'sudo ip route flush table rt2'
            check_call(cmd.split(), stdout=PIPE, stderr=PIPE)

            cmd = 'sudo ip route add 10.%s.%s.0/24 dev %s src 10.%s.%s.1 table rt2' % (
                iface, subnet, ifaces[iface], iface, subnet
            )
            check_call(cmd.split(), stdout=PIPE, stderr=PIPE)

            cmd = 'sudo ip route add 10.0.0.0/8 via 10.%s.%s.2 dev %s table rt2' % (
                iface, subnet, ifaces[iface]
            )
            check_call(cmd.split(), stdout=PIPE, stderr=PIPE)

            cmd = 'sudo ip rule add from 10.%s.0.0/16 table rt2' % iface
            check_call(cmd.split(), stdout=PIPE, stderr=PIPE)

        else:
            cmd = 'sudo ip route add 10.0.0.0/8 via 10.%s.%s.2 dev %s' % (
                iface, subnet, ifaces[iface]
            )
            check_call(cmd.split(), stdout=PIPE, stderr=PIPE)
