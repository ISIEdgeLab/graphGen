#! /usr/bin/env python
__version__ = "0.1.0"

import argparse
import csv
import re

import networkx as nx

import matplotlib
# Force matplotlib to not use any Xwindows backend
# must be set before importing pyplot
matplotlib.use('Agg')
# flake8: noqa=E402
# pylint: disable=wrong-import-position
import matplotlib.pyplot as plt

#pylint: disable=relative-import
import click_gen as click_gen
import ns_gen as ns_gen

# networkx 2.x is not backwards compatable with 1.x
__NX_VERSION__ = int(nx.__version__.split('.')[0])


def read_graph(filename):
    graph_obj = nx.read_edgelist(filename)
    push_elements = nx.get_edge_attributes(graph_obj, 's_elements')
    pull_elements = nx.get_edge_attributes(graph_obj, 'l_elements')
    for edge in nx.edges(graph_obj):
        if edge not in push_elements:
            push_elements[edge] = []
        if edge not in pull_elements:
            pull_elements[edge] = []

    for node in nx.nodes(graph_obj):
        if re.match("o[0-9]+", node):
            graph_obj.node[node]['external'] = True
    if __NX_VERSION__ > 1:
        nx.set_edge_attributes(graph_obj, push_elements, 's_elements')
        nx.set_edge_attributes(graph_obj, pull_elements, 'l_elements')
    else:
        nx.set_edge_attributes(graph_obj, 's_elements', push_elements)
        nx.set_edge_attributes(graph_obj, 'l_elements', pull_elements)
    return graph_obj


class GraphGen(object):

    def __init__(self, filename, routes=None, cmdline=dict):
        self.ns_gen = ns_gen.NSGen(cmdline)
        self.click_gen = click_gen.ClickGen(None, None, cmdline.__dict__)

        self.graph = read_graph(filename)
        # need to remove iteritems for py3 compatibility
        self.generate_ifaces()
        self.generate_ips()
        self.distribute_ifaces()
        if routes != None:
            self.read_routes(routes)
        self.distribute_ips()
        self.ns_gen.set_graph(self.graph)

    def draw_graph(self, filename="graph.png"):
        pos = nx.spring_layout(self.graph)
        nx.draw_networkx(self.graph, pos, font_size=10, node_color='k', font_color='w')
        plt.axis('off')
        plt.savefig(filename)

    # pylint: disable=too-many-locals, too-many-branches
    def generate_ifaces(self):
        ifs = {}
        others = {}
        enclaves = {}
        routers = {}
        e_links = {}
        for node in nx.nodes(self.graph):
            if re.match("e[0-9]+", node):
                enclaves[node] = node
            else:
                if re.match("o[0-9]+", node):
                    ifs[node] = ['if%s' % node]
                    others[node] = ['if%s' % node]

        if __NX_VERSION__ > 1:
            nx.set_node_attributes(self.graph, enclaves, 'enclaves')
        else:
            nx.set_node_attributes(self.graph, 'enclaves', enclaves)

        elist = list(enclaves)
        elist.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))

        # find primary link if specified
        self.check_primaries()
        primaries = nx.get_edge_attributes(self.graph, 'primary')

        mh_counter = 50
        for node in elist:
            neighbors = [x for x in self.graph.neighbors(node)]
            neighbors.sort(key=lambda neighbor: int(re.search('[0-9]+', neighbor).group(0)))
            for neighbor in neighbors:
                link = (node, neighbor)
                link_rev = (neighbor, node)
                if link in primaries or link_rev in primaries:
                    to_add = "if%d" % int(re.search('[0-9]+', node).group(0))
                else:
                    to_add = "if%d" % (mh_counter + int(re.search('[0-9]+', node).group(0)))
                elink = (node, to_add, neighbor)
                if node not in ifs:
                    ifs[node] = [to_add]
                    e_links[node] = [elink]
                else:
                    ifs[node].append(to_add)
                    e_links[node].append(elink)

                if neighbor not in routers:
                    routers[neighbor] = [to_add]
                else:
                    routers[neighbor].append(to_add)

        if __NX_VERSION__ > 1:
            nx.set_node_attributes(self.graph, routers, 'in_routers')
            nx.set_node_attributes(self.graph, others, 'others')
            nx.set_node_attributes(self.graph, ifs, 'ifs')
            nx.set_node_attributes(self.graph, e_links, 'elinks')
        else:
            nx.set_node_attributes(self.graph, 'in_routers', routers)
            nx.set_node_attributes(self.graph, 'others', others)
            nx.set_node_attributes(self.graph, 'ifs', ifs)
            nx.set_node_attributes(self.graph, 'elinks', e_links)

    def check_primaries(self):
        primaries = nx.get_edge_attributes(self.graph, 'primary')
        enclaves = nx.get_node_attributes(self.graph, 'enclaves')
        elist = list(enclaves)
        elist.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))

        for node in elist:
            neighbors = [x for x in self.graph.neighbors(node)]
            has_primary = False
            for neigh in neighbors:
                link1 = (node, neigh)
                link2 = (neigh, node)
                if link1 in primaries or link2 in primaries:
                    has_primary = True
                    break
            if not has_primary and neighbors:
                self.graph[node][neighbors[0]]['primary'] = True


    def generate_ips(self):
        ips = {}
        for node in nx.nodes(self.graph):
            if not (re.match("e[0-9]+", node) or re.match("o[0-9]+", node)):
                ips[node] = "10.100.150.%s" % node
        if __NX_VERSION__ > 1:
            nx.set_node_attributes(self.graph, ips, 'ips')
        else:
            nx.set_node_attributes(self.graph, 'ips', ips)


    def read_routes(self, filename):
        file_handle = open(filename, "r")
        input_rts = csv.reader(file_handle, delimiter=" ")
        routes = nx.get_node_attributes(self.graph, 'routes')

        for route in input_rts:
            target = route[0]
            iface = 'if%s' % re.search("[0-9]+", target).group(0)
            for route_num in range(1, len(route) - 1):
                router = route[route_num]
                next_hop = route[route_num + 1]
                if router == " " or router == "" or next_hop == " " or next_hop == "":
                    #probably should output an error here!
                    continue
                routes[router]['ifaces'][iface] = next_hop



    def distribute_ifaces(self):
        routes = {}
        for node in nx.nodes(self.graph):
            routes[node] = {'ifaces': {}, 'ips': {}, 'costs': {}}

        elinks = nx.get_node_attributes(self.graph, 'elinks')

        # need to determine proper link!
        # pylint: disable=too-many-nested-blocks
        for node, ifaces in nx.get_node_attributes(self.graph, 'ifs').items():
            e_nodes = nx.get_node_attributes(self.graph, 'ifs')

            for link in elinks[node]:
                g_tmp = self.graph.copy()

                #for inode in nx.get_node_attributes(self.graph, 'ifs'):
                #    if node != inode:
                #        g_tmp.remove_node(inode)

                counter = 0
                for link_tmp in elinks[node]:
                    if link != link_tmp:
                        g_tmp.add_edge("dummy%d" % counter, link_tmp[2])
                        g_tmp.remove_edge(node, link_tmp[2])
                        counter = counter + 1
                weights = nx.get_edge_attributes(g_tmp, 'weight')
                for onode in e_nodes:
                    if not onode == node:
                        for edge in nx.edges(g_tmp, onode):
                            weights[edge] = 10000

                # NEED TO CLEAN THIS CRAP UP!
                if __NX_VERSION__ > 1:
                    nx.set_edge_attributes(g_tmp, weights, 'weight')
                else:
                    nx.set_edge_attributes(g_tmp, 'weight', weights)
                paths = nx.single_source_dijkstra_path(g_tmp, node, weight='weight')
                for _, path in paths.items():
                    cost = 1
                    for path_num in range(1, len(path)):
                        edge = (path[path_num - 1], path[path_num])
                        for iface in ifaces:
                            if edge[0] == node and not re.match("dummy*", edge[1]):
                                if iface == link[1]:
                                    routes[edge[1]]['ifaces'][iface] = edge[0]
                                    routes[edge[1]]['costs'][iface] = cost
                                elif iface not in routes[edge[1]]['ifaces']:
                                    routes[edge[1]]['ifaces'][iface] = edge[0]
                                    routes[edge[1]]['costs'][iface] = cost
                            else:
                                if not (re.match("dummy*", edge[0]) or\
                                    (re.match("dummy*", edge[1])) or edge[0] in e_nodes) and\
                                    (iface in routes[edge[0]]['ifaces']):
                                    if iface == link[1]:
                                        routes[edge[1]]['ifaces'][iface] = edge[0]
                                        routes[edge[1]]['costs'][iface] = cost
                                    elif iface not in routes[edge[1]]['ifaces']:
                                        routes[edge[1]]['ifaces'][iface] = edge[0]
                                        routes[edge[1]]['costs'][iface] = cost
                            if edge[0] in e_nodes and edge[0] != node:
                                cost = cost + 10000
                            else:
                                cost = cost + 1


        if __NX_VERSION__ > 1:
            nx.set_node_attributes(self.graph, routes, 'routes')
        else:
            nx.set_node_attributes(self.graph, 'routes', routes)

    def distribute_ips(self):
        routes = nx.get_node_attributes(self.graph, 'routes')
        for node, ip_addr in nx.get_node_attributes(self.graph, 'ips').items():
            for edge in list(nx.bfs_edges(self.graph, node)):
                routes[edge[1]]['ips'][ip_addr] = edge[0]

        if __NX_VERSION__ > 1:
            nx.set_node_attributes(self.graph, routes, 'routes')
        else:
            nx.set_node_attributes(self.graph, 'routes', routes)

    def write_routes(self, filename):
        file_handle = open(filename, 'w')
        routes = nx.get_node_attributes(self.graph, 'routes')
        e_nodes = nx.get_node_attributes(self.graph, 'ifs')
        in_routers = nx.get_node_attributes(self.graph, 'in_routers')
        elinks = nx.get_node_attributes(self.graph, 'elinks')

        for node in e_nodes:
            route = routes[node]['ifaces']
            cost = routes[node]['costs']
            for iface, forward in route.items():
                enclave = re.search('[0-9]+', node).group(0)
                prefix = re.search('[0-9]+', iface).group(0)
                for link in elinks[node]:
                    #elinks is a 3 tuple of (node, interface, forwarder)
                    if link[1] in in_routers[forward]:
                        forward = re.search('[0-9]+', link[1]).group(0)
                        break

                if cost[iface] >= 20000:
                    forward = 0
                output = 'ct%s %s %s %d\n' % (enclave, prefix, forward, cost[iface])
                file_handle.write(output)
        file_handle.close()



    def get_paths(self):
        e_nodes = nx.get_node_attributes(self.graph, 'ifs')

        paths = {}

        ifs = []
        for node in e_nodes:
            ifs.extend(e_nodes[node])

        # Build Paths
        for node in e_nodes:
            paths[node] = []
            for iface in ifs:
                if iface not in e_nodes[node]:
                    new_path = self.discover_path(node, iface)
                    if new_path != []:
                        prefix = re.search('[0-9]+', iface).group(0)
                        new_path.insert(0, "10.%s.0.0/16" % prefix)
                        paths[node].append(new_path)

        return paths


    def write_paths(self, filename):
        file_handle = open(filename, 'w')
        e_nodes = nx.get_node_attributes(self.graph, 'ifs')

        paths = self.get_paths()

        for node in e_nodes:
            for path in paths[node]:
                path_line = ", ".join(path)
                file_handle.write("%s\n" % path_line)

        file_handle.close()

    def discover_path(self, src, dest):
        routes = nx.get_node_attributes(self.graph, 'routes')
        e_nodes = nx.get_node_attributes(self.graph, 'ifs')

        curr = src
        path = []
        done = False
        while not done:
            path.append(curr)
            if curr in e_nodes and dest in e_nodes[curr]:
                done = True
            else:
                if routes[curr]['costs'][dest] > 20000:
                    path = []
                    done = True
                else:
                    curr = routes[curr]['ifaces'][dest]
        return path

    def write_click(self, filename):
        self.click_gen.writeClick(self.graph, filename)

    def write_ns(self):
        self.ns_gen.writeNS()

def main():
    hardware_types = [
        'dl380g3', 'MicroCloud', 'pc2133', 'pc2133', 'bpc2133', 'pc3000', 'bpc3000', 'pc3060',
        'bpc3060', 'pc3100', 'bvx2200', 'bpc2800', 'netfpga2', 'sm', 'smX10',
        ]
    parser = argparse.ArgumentParser(description='Create click config given a graph.')
    parser.add_argument(
        'infile', type=str, help='Input graph file in any recognized networkx format'
    )
    parser.add_argument(
        '-d', dest='draw_output',
        help='Draw the given input file and store in the given destination',
    )
    parser.add_argument('-n', dest='ns_file', help='Write an ns file as well')
    parser.add_argument(
        '-o', dest='output', default='vrouter.template',
        help='Specify output for click template (default: vrouter.template)',
    )
    parser.add_argument(
        '-r', dest='routes', type=str, help='Specify input routes in the given ssv file'
    )
    parser.add_argument(
        '--click-hardware', type=str, dest='clickHardware', default='dl380g3',
        choices=hardware_types,
        help='Specify the specific hardware device you would like to use for Click',
    )
    parser.add_argument(
        '--crypto-hardware', type=str, dest='cryptoHardware', default='MicroCloud',
        choices=hardware_types,
        help='Specify the specific hardware device you would like to use for Enclave crypto device',
    )
    parser.add_argument(
        '--client-hardware', type=str, dest='clientHardware', default='MicroCloud',
        choices=hardware_types,
        help='Specify the specific hardware device you would like to use for client/servers',
    )
    parser.add_argument(
        '--ct-hardware', type=str, dest='ctHardware', default='MicroCloud',
        choices=hardware_types,
        help='Specify the specific hardware device you would like to use for CT nodes',
    )
    parser.add_argument(
        '--bandwidth', type=str, dest='bw', default='1Gbps',
        # Note: DETER has awkward implementation for links less than 100Mbps that is painful
        choices=['100Mbps', '1000Mbps', '1Gbps', '10000Mbps', '10Gbps'],
        help='Default Bandwidth for each link (1Gbps)',
    )
    parser.add_argument(
        '--delay', dest='delay', default='0ms', help='Default Delay for each link (0ms)'
    )
    parser.add_argument(
        '--loss', dest='loss', type=float, default=0.0,
        help='Default Loss rate for each link (0.0)',
    )
    parser.add_argument(
        '--set-startcmd', dest='startCmd', default="",
        help='Set a default start command to run on all nodes'
    )
    parser.add_argument(
        '--CT-OS', dest='ct_os', default="Ubuntu1404-64-STD",
        help="Specify you're own OS for CT nodes"
    )
    parser.add_argument(
        '--default-OS', dest='os', default="Ubuntu1404-64-STD",
        help="Default OS for non CT nodes"
    )
    parser.add_argument(
        '--num-servers', dest='numServers', default=1, help='Number of servers per enclave'
    )
    parser.add_argument(
        '--num-clients', dest='numClients', default=8, help='Number of \"traf\" nodes per enclave'
    )
    parser.add_argument(
        '--access-link-constraints', dest='inConstraints', default=False,
        action='store_const', const=True,
        help='Add link constraints to the access links for the vrouter',
    )
    parser.add_argument(
        '--enable-dpdk', dest='useDPDK', default=True,
        action='store_const', const=True,
        help='Create Click template for DPDK support (note DPDK automatically enables ARP)',
        )
    parser.add_argument(
        '--enable-ARP', dest='arp', default=False, action='store_const', const=True,
        help='Configure click to use ARP',
    )
    parser.add_argument(
        '--disable-codel', dest='useCodel', default=True, action='store_const', const=False,
        help='Disable CoDel on all links',
    )
    parser.add_argument(
        '--disable-containers', dest='useContainers', default=True,
        action='store_const', const=False,
        help='Disable Containerization',
    )
    parser.add_argument(
        '--disable-crypto-nodes', dest='useCrypto', default=True, action='store_const', const=False,
        help='Do not add any crypto nodes to enclaves',
    )
    parser.add_argument(
        '--write-routes', dest='write_routes', default=False, action='store_const', const=True,
        help='Write routes when using multi-homing',
    )
    parser.add_argument(
        '--write-paths', dest='write_paths', default="",
        help='Write enclave routing paths to the specified file',
    )
    parser.add_argument(
        '--version', action='version',
        version='%(prog)s {version}'.format(version=__version__)
    )

    args = parser.parse_args()

    gen = GraphGen(args.infile, args.routes, args)

    if args.write_routes:
        gen.write_routes('enclave.routes')
    if args.write_paths:
        gen.write_paths(args.write_paths)
    if args.draw_output:
        gen.draw_graph(args.draw_output)
    gen.write_click(args)
    if args.ns_file:
        gen.write_ns()
    if args.help:
        args.print_help()
        exit(1)
    if args.version:
        exit(1)

if __name__ == "__main__":
    main()
