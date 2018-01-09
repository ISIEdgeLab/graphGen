#! /usr/bin/env python

import networkx as nx
# networkx 2.x is not backwards compatable with 1.x
__NX_VERSION__ = int(nx.__version__.split('.')[0])

import matplotlib
# Force matplotlib to not use any Xwindows backend.
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import re, csv, sys
import clickGen as cg
import nsGen as ng
import argparse

class GraphGen():

    def __init__(self, filename, routes=None, cmdline=[]):
        self.g = None
        self.ng = ng.NSGen(None, None, cmdline)
        self.cg = cg.ClickGen(None, None, cmdline)

        self.readGraph(filename)
        self.generateIFs()
        self.generateIPs()
        self.distributeIFs()
        if routes != None:
            self.readRoutes(routes)
        self.distributeIPs()

    def readGraph(self, filename):
        self.g = nx.read_edgelist(filename)
        push_elements = nx.get_edge_attributes(self.g, 's_elements')
        pull_elements = nx.get_edge_attributes(self.g, 'l_elements')
        for edge in nx.edges(self.g):
            if edge not in push_elements:
                push_elements[edge] = []
            if edge not in pull_elements:
                pull_elements[edge] = []
                
        for node in nx.nodes(self.g):
            if re.match("o[0-9]+",  node):
                self.g.node[node]['external'] = True
        if __NX_VERSION__ > 1:
            nx.set_edge_attributes(self.g, push_elements, 's_elements')
            nx.set_edge_attributes(self.g, pull_elements, 'l_elements')
        else:
            nx.set_edge_attributes(self.g, 's_elements', push_elements)
            nx.set_edge_attributes(self.g, 'l_elements', pull_elements)

                
    def drawGraph(self, filename="graph.png"):
        pos = nx.spring_layout(self.g)
        #pos=nx.graphviz_layout(self.g)
        #nx.draw_networkx_nodes(self.g, pos)
        #nx.draw_networkx_edges(self.g, pos)
        nx.draw_networkx(self.g, pos, font_size=10, node_color='k', font_color='w')
        plt.axis('off')
        #nx.write_dot(self.g, "graph.dot");
        plt.savefig(filename)

    def generateIFs(self):
        ifs = {}
        others = {}
        enclaves = {}
        routers = {}
        e_links = {}
        for node in nx.nodes(self.g):
            if re.match("e[0-9]+", node):
                enclaves[node] = node
            else:
                if re.match("o[0-9]+", node):
                    ifs[node] = ['if%s' % node]
                    others[node] = ['if%s' % node]

        if __NX_VERSION__ > 1:
            nx.set_node_attributes(self.g, enclaves, 'enclaves')
        else:
            nx.set_node_attributes(self.g, 'enclaves', enclaves)
                    
        elist = list(enclaves)
        elist.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))
        
        # find primary link if specified
        self.checkPrimaries()
        primaries = nx.get_edge_attributes(self.g, 'primary')
        
        mh_counter = 50
        for node in elist:
            neighbors = [x for x in self.g.neighbors(node)]
            neighbors.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))
            for x in neighbors:
                link = (node, x)
                link_rev = (x, node)
                if link in primaries or link_rev in primaries:
                    toAdd = "if%d" % int(re.search('[0-9]+', node).group(0))
                else:
                    toAdd = "if%d" % (mh_counter + int(re.search('[0-9]+', node).group(0)))
                    
                elink = (node, toAdd, x)
                if node not in ifs:
                    ifs[node] = [toAdd]
                    e_links[node] = [elink]
                else:
                    ifs[node].append(toAdd)
                    e_links[node].append(elink)

                if x not in routers:
                    routers[x] = [toAdd]
                else:
                    routers[x].append(toAdd)
                                
        if __NX_VERSION__ > 1:
            nx.set_node_attributes(self.g, routers, 'in_routers')
            nx.set_node_attributes(self.g, others, 'others')
            nx.set_node_attributes(self.g, ifs, 'ifs')
            nx.set_node_attributes(self.g, e_links, 'elinks')
        else:
            nx.set_node_attributes(self.g, 'in_routers', routers)
            nx.set_node_attributes(self.g, 'others', others)
            nx.set_node_attributes(self.g, 'ifs', ifs)
            nx.set_node_attributes(self.g, 'elinks', e_links)

    def checkPrimaries(self):
        primaries = nx.get_edge_attributes(self.g, 'primary')
        enclaves = nx.get_node_attributes(self.g, 'enclaves')
        elist = list(enclaves)
        elist.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))
        
        for node in elist:
            neighbors = [x for x in self.g.neighbors(node)]
            hasPrimary = False
            for neigh in neighbors:
                link1 = (node, neigh)
                link2 = (neigh, node)
                if link1 in primaries or link2 in primaries:
                    hasPrimary = True
                    break
            if not hasPrimary and len(neighbors) > 0:
                self.g[node][neighbors[0]]['primary'] = True
            
        
    def generateIPs(self):
        ips = {}
        for node in nx.nodes(self.g):
            if not (re.match("e[0-9]+", node) or re.match("o[0-9]+", node)):
                ips[node] = "10.100.150.%s" % node
        if __NX_VERSION__ > 1:
            nx.set_node_attributes(self.g, ips, 'ips')
        else:
            nx.set_node_attributes(self.g, 'ips', ips)


    def readRoutes(self, filename):
        fh = open(filename, "r")
        input_rts = csv.reader(fh, delimiter=" ")
        routes = nx.get_node_attributes(self.g, 'routes')

        for route in input_rts:
            target = route[0]
            iface = 'if%s' % re.search("[0-9]+", target).group(0)
            for x in range(1, len(route) - 1):
                router = route[x]
                next_hop = route[x + 1]
                if router == " " or router == "" or next_hop == " " or next_hop == "":
                    #probably should output an error here!
                    continue
                routes[router]['ifaces'][iface] = next_hop
                    
        
        
    def distributeIFs(self):
        routes = {}
        for node in nx.nodes(self.g):
            routes[node] = {'ifaces': {}, 'ips': {}, 'costs': {}}

        elinks = nx.get_node_attributes(self.g, 'elinks')

        # need to determine proper link!
        
        for node,ifaces in nx.get_node_attributes(self.g, 'ifs').iteritems():

            e_nodes = nx.get_node_attributes(self.g, 'ifs')
            
            for link in elinks[node]:
                g_tmp = self.g.copy()

                #for inode in nx.get_node_attributes(self.g, 'ifs'):
                #    if node != inode:
                #        g_tmp.remove_node(inode)
                        
                c = 0
                for link_tmp in elinks[node]:
                    if link != link_tmp:
                        g_tmp.add_edge("dummy%d" % c, link_tmp[2])
                        g_tmp.remove_edge(node, link_tmp[2])
                        c = c + 1
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
                for src, path in paths.iteritems():
                    cost = 1
                    for x in range(1, len(path)):
                        edge = (path[x - 1], path[x])
                        for iface in ifaces:
                            if edge[0] == node and not re.match("dummy*", edge[1]):
                                if iface == link[1]:
                                    routes[edge[1]]['ifaces'][iface] = edge[0]
                                    routes[edge[1]]['costs'][iface] = cost
                                elif iface not in routes[edge[1]]['ifaces']:
                                    routes[edge[1]]['ifaces'][iface] = edge[0]
                                    routes[edge[1]]['costs'][iface] = cost
                            else:
                                if not (re.match("dummy*", edge[0]) or (re.match("dummy*", edge[1])) or
                                        edge[0] in e_nodes) and (iface in routes[edge[0]]['ifaces']):
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
            nx.set_node_attributes(self.g, routes, 'routes')
        else:
            nx.set_node_attributes(self.g, 'routes', routes)

    def distributeIPs(self):
        routes = nx.get_node_attributes(self.g, 'routes')
        for node, ip in nx.get_node_attributes(self.g, 'ips').iteritems():  
            for edge in list(nx.bfs_edges(self.g, node)):
                routes[edge[1]]['ips'][ip] = edge[0]

        if __NX_VERSION__ > 1:
            nx.set_node_attributes(self.g, routes, 'routes')
        else:
            nx.set_node_attributes(self.g, 'routes', routes)
        
    def writeRoutes(self, filename):
        fh = open(filename, 'w')
        routes = nx.get_node_attributes(self.g, 'routes')
        e_nodes = nx.get_node_attributes(self.g, 'ifs')
        in_routers = nx.get_node_attributes(self.g, 'in_routers')
        elinks = nx.get_node_attributes(self.g, 'elinks')
        
        for node in e_nodes:
            route = routes[node]['ifaces']
            cost = routes[node]['costs']
            for iface, forward in route.iteritems():
                enclave = re.search('[0-9]+', node).group(0)
                prefix = re.search('[0-9]+', iface).group(0)
                for link in elinks[node]:
                    #elinks is a 3 tuple of (node, interface, forwarder)
                    if link[1] in in_routers[forward]:
                        forward = re.search('[0-9]+', link[1]).group(0)
                        break;
                
                if cost[iface] >= 20000:
                    forward = 0
                output = 'ct%s %s %s %d\n' % (enclave, prefix, forward, cost[iface])
                fh.write(output)
        fh.close()



    def getPaths(self):
        e_nodes = nx.get_node_attributes(self.g, 'ifs')

        paths = {}

        ifs = []
        for node in e_nodes:
            ifs.extend(e_nodes[node])
            
        # Build Paths
        for node in e_nodes:
            paths[node] = []
            for iface in ifs:
                if iface not in e_nodes[node]:
                    newPath = self.discoverPath(node, iface)
                    if newPath != []:
                        prefix = re.search('[0-9]+', iface).group(0)
                        newPath.insert(0, "10.%s.0.0/16" % prefix)
                        paths[node].append(newPath)

        return paths


    def writePaths(self, filename):
        fh = open(filename, 'w')
        e_nodes = nx.get_node_attributes(self.g, 'ifs')

        paths = self.getPaths()

        for node in e_nodes:
            for path in paths[node]:
                path_line = ", ".join(path)
                fh.write("%s\n" % path_line)

        fh.close()

    def discoverPath(self, src, dest):
        routes = nx.get_node_attributes(self.g, 'routes')
        e_nodes = nx.get_node_attributes(self.g, 'ifs')
        
        curr = src
        path = []
        done = False
        while(not done):
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
                
        
        
    def writeClick(self, filename):
        self.cg.writeClick(self.g, filename)

    def writeNS(self, filename, args):
        self.ng.writeNS(self.g, filename, args)
        
def main():
    parser = argparse.ArgumentParser(description='Create click config given a graph.')
    parser.add_argument('infile', type=str, help='Input graph file in any recognized networkx format')
    parser.add_argument('-d', dest='draw_output', help='Draw the given input file and store in the given destination')
    parser.add_argument('-n', dest='ns_file', help='Write an ns file as well')
    parser.add_argument('-o', dest='output', default='vrouter.template', help='Specify output for click template (default: vrouter.template)')
    parser.add_argument('-r', dest='routes', type=str, help='Specify input routes in the given ssv file')
    parser.add_argument('--bandwidth', dest='bw', default='1Gbps', help='Default Bandwidth for each link (1Gbps)')
    parser.add_argument('--delay', dest='delay', default='0ms', help='Default Delay for each link (0ms)')
    parser.add_argument('--loss', dest='loss', default='0.0', help='Default Loss rate for each link (0.0)')
    parser.add_argument('--set-startcmd', dest='startCmd', default="", help='Set a default start command to run on all nodes')
    parser.add_argument('--CT-OS', dest='ct_os', default="Ubuntu1404-64-STD", help="Specify you're own OS for CT nodes")
    parser.add_argument('--default-OS', dest='os', default="Ubuntu1404-64-STD", help="Default OS for non CT nodes")
    parser.add_argument('--num-servers', dest='numServers', default=1, help='Number of servers per enclave')
    parser.add_argument('--num-clients', dest='numClients', default=8, help='Number of \"traf\" nodes per enclave')
    parser.add_argument('--access-link-constraints', dest='inConstraints', default=False, action='store_const', const=True, help='Add link constraints to the access links for the vrouter')
    parser.add_argument('--enable-dpdk', dest='useDPDK', default=True, help='Create Click template designed for DPDK support (note DPDK support automatically enables ARP)', action='store_const', const=True)
    parser.add_argument('--enable-ARP', dest='arp', default=False, action='store_const', const=True, help='Configure click to use ARP')
    parser.add_argument('--disable-codel', dest='useCodel', default=True, help='Disable CoDel on all links', action='store_const', const=False)
    parser.add_argument('--disable-containers', dest='useContainers', default=True, help='Disable Containerization', action='store_const', const=False)
    parser.add_argument('--disable-crypto-nodes', dest='useCrypto', default=True, help='Do not add any crypto nodes to enclaves', action='store_const', const=False)
    parser.add_argument('--write-routes', dest='writeRoutes', default=False, help='Write routes when using multi-homing', action='store_const', const = True)
    parser.add_argument('--write-paths', dest='writePaths', default="", help='Write enclave routing paths to the specified file')

    args = parser.parse_args()

    gen = GraphGen(args.infile, args.routes, cmdline=sys.argv)

    if args.writeRoutes:
        gen.writeRoutes('enclave.routes')
    if args.writePaths != "":
        gen.writePaths(args.writePaths)
    if args.draw_output != None:
        gen.drawGraph(args.draw_output)
    gen.writeClick(args)
    if args.ns_file != None:
        gen.writeNS(args.ns_file, args)

if __name__ == "__main__":
    main()


