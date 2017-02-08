#! /usr/bin/env python

from subprocess import Popen, PIPE, check_call, CalledProcessError, STDOUT
import socket

(output, error) = Popen(["ip", "route"], stdout = PIPE, stderr = PIPE).communicate()
out = output.splitlines()

lines_to_remove = []
ifaces = {}

for line in out:
    tokens = line.strip("\n").split()
    if (len(tokens) >= 5 and tokens[1] == "via" and
        tokens[0] != 'default' and
        (tokens[0] != '192.168.0.0/22' and tokens[0] != '172.16.0.0/12' and
         tokens[0] != '192.168.0.0/16' and tokens[0] != '224.0.0.0/4')):
        lines_to_remove.append(line)
    else:
        if (tokens[0] != 'default' and
            (tokens[0] != '192.168.0.0/22' and tokens[0] != '172.16.0.0/12' and
             tokens[0] != '192.168.0.0/16' and tokens[0] != '224.0.0.0/4')):
            quad = tokens[0].split('.')
            if quad[2] == '2':
                ifaces[quad[1]] = tokens[2]


in_routes = open('/tmp/enclave.routes', 'r')
sn = socket.gethostname().split('.')[0]

for line in lines_to_remove:
    route_to_rem = 'sudo ip route del %s' % line
    check_call(route_to_rem.split(), stdout = PIPE, stderr = PIPE)

for line in in_routes:
    tokens = line.strip("\n").split()
    if tokens[0] == sn and tokens[2] != "0":
        route_to_add = 'sudo ip route add 10.%s.0.0/16 via 10.%s.2.2 dev %s' % (tokens[1], tokens[2], ifaces[tokens[2]])
        check_call(route_to_add.split(),  stdout = PIPE, stderr = PIPE)
        
