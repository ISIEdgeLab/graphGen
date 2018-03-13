#!/bin/python
import sys
import time
import logging
import os
import json
import argparse
from subprocess import Popen, PIPE, check_call, CalledProcessError, STDOUT
import re
from string import Template

import netaddr as na
import netifaces as ni

LOGGER = logging.getLogger(__name__)


def get_hosts(path):
    ''' read local /etc/hosts file and return an {ip: hostname, ...} dict of the info found there'''
    ret = {}
    with open(path, 'r') as path_fd:
        for line in path_fd:
            line = line.strip('\n')
            # 10.0.1.3    xander-landos xander-0 xander
            reg_match = re.match(r'([\d\.]+)\s+([^ ]+)', line)
            if reg_match:
                ret[reg_match.group(1)] = reg_match.group(2)
    return ret


class OneHopNeighbors(object):
    def __init__(self):
        super(OneHopNeighbors, self).__init__()
        Popen(["apt-get", "install", "traceroute", "-y"], stdout=PIPE, stderr=PIPE).communicate()
        self.hosts = get_hosts('/etc/hosts')
        self.dpdk = False

    def get_neighbors(self):
        (local_addrs, local_nets) = self.get_local_addresses()
        if not local_addrs:
            LOGGER.warn('Unable to get local addresses - cannot continue.')
            return None
        devnull = open(os.devnull, 'w')
        one_hop_nbrs = {}
        for addr, host in self.hosts.iteritems():
            LOGGER.debug('comp: %s <--> %s', addr, local_addrs.keys())
            if addr not in local_addrs.values():
                ip_addr = na.IPAddress(addr)
                for lhost, network in local_nets.iteritems():
                    if ip_addr in network:
                        cmd = 'ping -c 1 {}'.format(addr)
                        try:
                            check_call(cmd.split(' '), stdout=devnull, stderr=STDOUT)
                        except (OSError, ValueError) as err:
                            LOGGER.warn('Unable to run "%s": %s', cmd, str(err))
                            continue
                        except CalledProcessError:
                            LOGGER.info(
                                '%s (%s) does not appear to be one hop neighbor.', lhost, addr
                            )
                            continue

                # so at this point, it looks like this host entry is a one hop
                # neighbor. Add it to the list.
                one_hop_nbrs[host] = addr

        return one_hop_nbrs

    def get_local_addresses(self):
        try:
            ifconfig_out, _ = Popen(['ifconfig'], stdout=PIPE).communicate()
        except (OSError, ValueError) as err:
            LOGGER.critical('Unable to read interface information via ifconfig: %s', str(err))
            return False

        local_addrs = {'localhost': '127.0.0.1'}
        local_nets = {}
        for line in ifconfig_out.split('\n'):
            # inet addr:10.0.6.2  Bcast:10.0.6.255  Mask:255.255.255.0
            reg_match = re.search(r'addr:([\d\.]+)\s+Bcast:([\d\.]+)\s+Mask:([\d\.]+)', line)
            if reg_match:
                if reg_match.group(1) in self.hosts.keys():
                    local_addrs[self.hosts[reg_match.group(1)]] = reg_match.group(1)
                    local_nets[self.hosts[reg_match.group(1)]] = na.IPNetwork(
                        "%s/%s" % (reg_match.group(1), reg_match.group(3))
                    )
                else:
                    LOGGER.warn(
                        'Found unnamed address in local interfaces (probably control '
                        'net): %s', reg_match.group(1)
                    )

        LOGGER.debug('local addresses: %s', local_addrs)
        return (local_addrs, local_nets)

# pylint: disable=too-few-public-methods
class RouteUpdate(object):
    def __init__(self):
        output, _ = Popen(["ip", "route"], stdout=PIPE, stderr=PIPE).communicate()
        out = output.splitlines()

        self.lines_to_remove = []
        self.ifaces = []

        for line in out:
            tokens = line.strip("\n").split()
            # pylint: disable=too-many-boolean-expressions
            if (len(tokens) >= 5 and tokens[1] == "via" and tokens[0] != 'default' and
                    (tokens[0] != '192.168.0.0/22' and tokens[0] != '172.16.0.0/12' and
                     tokens[0] != '192.168.0.0/16' and tokens[0] != '224.0.0.0/4')):
                self.lines_to_remove.append(line)
            else:
                if (tokens[0] != 'default' and
                        (tokens[0] != '192.168.0.0/22' and tokens[0] != '172.16.0.0/12' and
                         tokens[0] != '192.168.0.0/16' and tokens[0] != '224.0.0.0/4')):
                    self.ifaces.append(tokens[2])


    def update_routes(self):
        for line in self.lines_to_remove:
            route_to_rem = 'sudo ip route del %s' % line
            check_call(route_to_rem.split(), stdout=PIPE, stderr=PIPE)

        for iface in self.ifaces:
            addrs = ni.ifaddresses(iface)
            ip_addr = na.IPAddress(addrs[ni.AF_INET][0]['addr'])
            net = na.IPNetwork('%s/255.255.0.0' % ip_addr)
            route_to_add = 'sudo ip route add %s via %s dev %s' % (net.cidr, (ip_addr - 1), iface)
            print route_to_add
            check_call(route_to_add.split(), stdout=PIPE, stderr=PIPE)


# pylint: disable=too-many-instance-attributes
class ClickConfig(object):
    def __init__(self, vargs):
        self.template_file = "/tmp/vrouter.template"
        self.out_file = "/tmp/vrouter.click"
        self.input_file = "/tmp/ifconfig.json"
        self.routes_file = "/tmp/routes.json"
        self.nbrs = OneHopNeighbors()
        self.nbrs.get_neighbors()

        self.args = vargs

        try:
            self.template = Template(open(self.template_file).read())
            self.tf_fd = open(self.template_file, "r")
        except IOError:
            sys.stderr.write("Cannot find template file\n")
            sys.exit(1)

        self.arpless = False
        self.use_dpdk = False
        for line in self.tf_fd:
            if "friend" in line:
                self.arpless = True
            if "$DPDKDeparture" in line:
                self.use_dpdk = True
        self.tf_fd.close()

        self.ifs = {}
        self.data = {}
        self.gws = []
        self.routes = {}

        if self.use_dpdk:
            self.install_dpdk()

    def install_dpdk(self):
        if os.path.exists(self.input_file):
            return
        out = open("/tmp/dpdk_config.out", "w")
        err = open("/tmp/dpdk_config.err", "w")
        os.environ["PATH"] += os.pathsep + '/proj/edgect/share/dpdk/bin'

        check_call("install-dpdk.sh", stdout=out, stderr=err)
        check_call("install-fastclick.sh", stdout=out, stderr=err)

        fh_inputs = open(self.input_file, "w")
        check_call("getifaces.py", stdout=fh_inputs, stderr=err)
        fh_inputs.close()

        fh_routes = open(self.routes_file, "w")
        check_call("getroutes.py", stdout=fh_routes, stderr=err)
        fh_routes.close()

        check_call("setup-dpdk.sh", stdout=out, stderr=err)
        out.close()
        err.close()


    def generate_inputs(self):
        fh_routes = open(self.routes_file)
        fh_inputs = open(self.input_file)
        inputs = json.load(fh_inputs)
        routes = json.load(fh_routes)

        our_routes = {}
        priv_slash8 = na.IPNetwork("10.0.0.0/8")
        for route in routes:
            if route['bits'] == "16" and na.IPAddress(route['net']) in priv_slash8:
                our_routes[route['prefix'].encode('ascii')] = route['nexthop']

        for info in inputs:
            if 'vlan' not in info:
                DPDKArrStr = self.data.get('DPDKArrival', "")
                DPDKDetStr = self.data.get('DPDKDeparture', "")
                DPDKArrStr = "%s\nFromDPDKDevice(%d) -> VLANDecap() -> vlanmux;" % (DPDKArrStr, info['port'])
                if self.args.burst != 0:
                    DPDKDetStr = "%s\noutDPDK%d :: ToDPDKDevice(%d, BURST %d);" % (DPDKDetStr, info['port'], info['port'], self.args.burst)
                else:
                    DPDKDetStr = "%s\noutDPDK%d :: ToDPDKDevice(%d);" % (DPDKDetStr, info['port'], info['port'])
                    
                self.data['DPDKArrival'] = DPDKArrStr
                self.data['DPDKDeparture'] = DPDKDetStr
            else:
                ifnum = int(info['ip'].split('.')[1])
                our16 = na.IPNetwork('%s/255.255.0.0' % info['ip'])
                self.data['vlan%d' % ifnum] = info['vlan']
                self.data['if%d' % ifnum] = info['interface']
                self.data['if%d_ip' % ifnum] = info['ip']
                self.data['if%d_eth' % ifnum] = info['hwaddr']
                self.data['if%d_16' % ifnum] = "%s" % our16.cidr
                self.data['if%d_gw' % ifnum] = our_routes["%s" % our16.cidr]
                self.data['out_if%d' % ifnum] = "outDPDK%d" % info['port']

        
    def parse_routing(self):
        (output, error) = Popen(["ip", "route"], stdout = PIPE, stderr = PIPE).communicate()
        out = output.splitlines()
        
        c = 1
        for line in out:
            tokens = line.strip("\n").split()
            if (len(tokens) >= 5 and tokens[1] == "via" and
                tokens[0] != 'default' and
                (tokens[0] != '192.168.0.0/22' and tokens[0] != '172.16.0.0/12' and
                 tokens[0] != '192.168.0.0/16' and tokens[0] != '224.0.0.0/4')):
                ifnum = int(tokens[2].split('.')[1])
                if ifnum == 100:
                    ifnum = int(tokens[2].split('.')[2])
                    self.ifs[tokens[4]] = "o%d" % ifnum
                    self.data['ifo%d' % ifnum] = tokens[4]
                    self.data['ifo%d_16' % ifnum] = tokens[0]
                    self.data['ifo%d_gw' % ifnum] = tokens[2]
                else:
                    self.ifs[tokens[4]] = "%d" % ifnum
                    self.data['if%d' % ifnum] = tokens[4]
                    self.data['if%d_16' % ifnum] = tokens[0]
                    self.data['if%d_gw' % ifnum] = tokens[2]
            elif (tokens[1] == "dev" and tokens[2] not in self.ifs and
                  (tokens[0] != '192.168.0.0/22' and tokens[0] != '172.16.0.0/12' and
                   tokens[0] != '192.168.0.0/16' and tokens[0] != '224.0.0.0/4')):
                ifnum = int(tokens[0].split('.')[1])
                if ifnum == 100:
                    ifnum = int(tokens[0].split('.')[2])
                    self.ifs[tokens[2]] = "o%d" % ifnum
                    self.data['ifo%d' % ifnum] = tokens[2]
                    self.data['ifo%d_16' % ifnum] = tokens[0]
                    self.data['ifo%d_gw' % ifnum] = ''
                else:
                    self.ifs[tokens[2]] = "%d" % ifnum
                    self.data['if%d' % ifnum] = tokens[2]
                    self.data['if%d_16' % ifnum] = tokens[0]
                    self.data['if%d_gw' % ifnum] = ''

    def process_arp(self):
        (output, error) = Popen(["arp", "-a"], stdout = PIPE, stderr = PIPE).communicate()
	
        out = output.splitlines()
        for line in out:
            tokens = line.strip("\n").split()
            if len(tokens) == 7 and tokens[0] != '?':
                if tokens[-1] in self.ifs:
                    self.data['if%s_friend' % self.ifs[tokens[-1]]]  = tokens[3]
                    
        
    def generate_route_str(self):
        route_str = ""
        dev_null = open('/dev/null', 'w')
        for ip, route in self.routes.iteritems():
            if route['gw'] != "":
                route_str = "%s,\n\t\t\t %s %s %d" % (route_str, ip, route['gw'],
                                              self.ifs.index(route['if']))
    
            else:
                route_str = "%s,\n\t\t\t %s %d" % (route_str, ip,
                                                   self.ifs.index(route['if']))
        self.data['routing'] = route_str
                
    def write_config(self):
        if not self.use_dpdk:
	    time.sleep(10)
        config = self.template.substitute(self.data)
        fh = open(self.out_file, "w")
        fh.write(config)
        fh.close()

    def updateConfig(self):
        if not self.use_dpdk:
            self.parse_routing()
            #self.generate_route_str()
            if self.arpless:
                self.process_arp()
        else:
            self.generate_inputs()
        
        self.write_config()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Update a click template with local state to correctly configure click.')
    parser.add_argument('-d', dest='debug', help='Enable debug statements')
    parser.add_argument('-v', dest='verbose', help='Enable verbose output (same as debug atm)')
    parser.add_argument('--burst', dest='burst', default=0, type=int, help='Set the output burst parameter for DPDK links')
    args = parser.parse_args()
    
    if args.debug or args.verbose:
        logging.basicConfig(filename='/tmp/click_config.LOGGER', level=logging.DEBUG)
    else:
        logging.basicConfig(filename='/tmp/click_config.LOGGER', level=logging.WARN)

    ru = RouteUpdate()
    ru.update_routes()
    uc = ClickConfig(args)
    uc.updateConfig()


