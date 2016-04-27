import networkx as nx
import matplotlib.pyplot as plt
import re
import clickGen as cg
import nsGen as ng
import argparse

class GraphGen():

    def __init__(self):
        self.g = None

    def readGraph(self, filename):
        self.g = nx.read_edgelist(filename)
        p_elements = nx.get_edge_attributes(self.g, 'p_elements')
        u_elements = nx.get_edge_attributes(self.g, 'u_elements')
        for edge in nx.edges(self.g):
            if edge not in p_elements:
                p_elements[edge] = []
            if edge not in u_elements:
                u_elements[edge] = []
            
        nx.set_edge_attributes(self.g, 'p_elements', p_elements)
        nx.set_edge_attributes(self.g, 'u_elements', u_elements)

                
    def drawGraph(self, filename="graph.png"):
        pos = nx.spring_layout(self.g)
        nx.draw_networkx_nodes(self.g, pos)
        nx.draw_networkx_edges(self.g, pos)
        nx.draw_networkx_labels(self.g, pos, font_size=10)
        plt.axis('off')
        plt.savefig(filename)

    def generateIFs(self):
        ifs = {}
        
        for node in nx.nodes(self.g):
            if re.match("e[0-9]+", node):
                ifs[node] = 'if%s' % re.search("[0-9]+", node).group(0)

        nx.set_node_attributes(self.g, 'ifs', ifs)

    def generateIPs(self):
        ips = {}
        for node in nx.nodes(self.g):
            if not re.match("e[0-9]+", node):
                ips[node] = "10.100.150.%s" % node
        nx.set_node_attributes(self.g, 'ips', ips)
        
    def distributeIFs(self):
        routes = {}
        for node in nx.nodes(self.g):
            routes[node] = {'ifaces': {}, 'ips': {}}
        
        for node,iface in nx.get_node_attributes(self.g, 'ifs').iteritems():  
            for edge in list(nx.bfs_edges(self.g, node)):
                routes[edge[1]]['ifaces'][iface] = edge[0]

        nx.set_node_attributes(self.g, 'routes', routes)

    def distributeIPs(self):
        routes = nx.get_node_attributes(self.g, 'routes')
        for node, ip in nx.get_node_attributes(self.g, 'ips').iteritems():  
            for edge in list(nx.bfs_edges(self.g, node)):
                routes[edge[1]]['ips'][ip] = edge[0]

        nx.set_node_attributes(self.g, 'routes', routes)
        
        
        
    def writeClick(self, filename):
        cg.writeClick(self.g, filename)

    def writeNS(self, filename, args):
        ng.writeNS(self.g, filename, args)
        
def main():
    parser = argparse.ArgumentParser(description='Create click config given a graph.')
    parser.add_argument('infile', type=str, help='Input graph file in any recognized networkx format')
    parser.add_argument('-d', dest='draw_output', help='Draw the given input file and store in the given destination')
    parser.add_argument('-n', dest='ns_file', help='Write an ns file as well')
    parser.add_argument('-o', dest='output', default='vrouter.template', help='Specify output for click template (default: vrouter.template)')
    parser.add_argument('-a', dest='arp', help='Configure click to use ARP')
    parser.add_argument('--bandwidth', dest='bw', default='1Gbps', help='Default Bandwidth for each link (1Gbps)')
    parser.add_argument('--delay', dest='delay', default='0ms', help='Default Delay for each link (0ms)')
    parser.add_argument('--loss', dest='loss', default='0.0', help='Default Loss rate for each link (0.0)')
    args = parser.parse_args()

    gen = GraphGen()
    gen.readGraph(args.infile)
    gen.generateIFs()
    gen.generateIPs()
    gen.distributeIFs()
    gen.distributeIPs()
    if args.draw_output != None:
        gen.drawGraph(args.draw_output)
    gen.writeClick(args)
    if args.ns_file != None:
        arg2 = {'os': "Ubuntu1404-64-STD"}
        gen.writeNS(args.ns_file, arg2)

if __name__ == "__main__":
    main()
