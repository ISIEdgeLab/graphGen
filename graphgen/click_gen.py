import re
import time

import networkx as nx
__NX_VERSION__ = int(nx.__version__.split('.')[0])


def get_capital_letters(in_str):
    out_str = ""
    for char in in_str:
        if char.isupper():
            out_str += char

    return out_str


# pylint: disable=too-many-instance-attributes
class ClickGen(object):
    def __init__(self, graph, args, cmdline):
        self.graph = graph
        self.args = args
        self.cmdline = cmdline
        self.num_inputs = None
        self.num_others = None
        self.in_routers = []
        self.graph_in_routers = None
        self.arp_less = None
        self.use_dpdk = None
        self.file_handler = None

    def write_click(self, graph, args):
        self.graph = graph
        self.args = args

        filename = self.args.output

        self.num_inputs = len(nx.get_node_attributes(self.graph, 'ifs'))
        self.num_others = len(nx.get_node_attributes(self.graph, 'others'))
        for node, _ in nx.get_node_attributes(self.graph, 'ifs').items():
            edges = nx.edges(self.graph, node)
            for edge in edges:
                if re.match("e[0-9]+", edge[0]) or re.match("o[0-9]+", edge[0]):
                    self.in_routers.append(int(edge[1]))
                else:
                    self.in_routers.append(int(edge[0]))
        self.in_routers.sort()
        self.graph_in_routers = list(nx.get_node_attributes(self.graph, 'in_routers').values())
        self.graph_in_routers.sort(key=lambda x: int(re.search('[0-9]+', x[0]).group(0)))

        self.arp_less = True
        self.use_dpdk = args.use_dpdk

        # DPDK must use arp
        if args.arp or args.use_dpdk:
            self.arp_less = False

        self.file_handler = open(filename, "w")

        self.write_preamble()
        self.write_routers()
        self.write_classifiers()
        if args.use_dpdk:
            self.write_vlan_multiplexing()
        self.write_packet_arrival()
        self.write_packet_departure()
        if self.arp_less:
            self.write_arp_less()
        if not self.arp_less:
            self.write_arp_handler()
        self.write_link_shaping()
        self.write_ttl_dec()
        self.write_links()
        self.write_teed_links()
        self.write_drop_packers_on_routers()
        self.write_routers_to_interfaces()
        self.write_local_delivery()
        self.file_handler.close()

    def write_preamble(self):
        tstr = time.asctime(time.gmtime(time.time()))

        self.file_handler.write(
            "// Auto generated Click Template using graphgen/click_gen.py at %s UTC" % tstr
        )
        if self.cmdline:
            self.file_handler.write("\n// Command line: %s \n\n" % dict(self.cmdline))

    def write_classifiers(self):
        self.file_handler.write("\n// Packet Classifiers\n")
        i = 1
        in_routers = self.graph_in_routers
        # Create classifiers
        for nodes in in_routers:
            for node in nodes:
                self.file_handler.write(
                    "c%d :: Classifier(12/0800, 12/0806 20/0001, 12/0806 20/0002, -);\n"
                    % int(re.search('[0-9]+', node).group(0)))
                i = i + 1
        self.file_handler.write(
            "chost :: Classifier(12/0800, 12/0806 20/0001, 12/0806 20/0002, -);\n"
        )

    def write_vlan_multiplexing(self):
        self.file_handler.write("\n// VLAN Multiplexing\n")
        in_routers = self.graph_in_routers
        vlanstr = ""
        for router_list in in_routers:
            for router in router_list:
                vlanstr = "%s, VLAN ${vlan%d}" % (
                    vlanstr, (int(re.search('[0-9]+', router).group(0)))
                )
        vlanstr = vlanstr[2:]
        self.file_handler.write("vlanmux :: VlanSwitch(%s);\n" % vlanstr)

    def write_packet_arrival(self):
        self.file_handler.write("\n// Packet Arrival\n")
        in_routers = self.graph_in_routers
        if self.use_dpdk:
            self.file_handler.write("$DPDKArrival\n")

            i = 0
            # FIX DO THIS RIGHT!  We'll start with just the standard mode
            for router_list in in_routers:
                for router in router_list:
                    self.file_handler.write(
                        "vlanmux[%d] -> c%d;\n" % (
                            i, int(re.search('[0-9]+', router).group(0)))
                    )
                    i = i + 1

        else:
            # FIX THIS TOO, for MULTI HOMING
            counter = 1
            for router in in_routers:
                self.file_handler.write(
                    "FromDevice(${if%d}) -> c%d;\n" % (
                        int(re.search('[0-9]+', router).group(0)), counter)
                )
                counter = counter + 1
            for i in range(self.num_others):
                self.file_handler.write("FromDevice(${ifo%d}) -> c%d;\n" % (i + 1, counter))
                counter = counter + 1

        self.file_handler.write("FromHost(fakedge0) -> chost;\n")

    # WE'RE HERE
    # NEED TO COMPLETELY RETHINK DPDK and INPUT/OUTPUT implementation

    def write_packet_departure(self):
        self.file_handler.write("\n// Packet Departure\n")
        in_routers = self.graph_in_routers
        if self.use_dpdk:
            self.file_handler.write("$DPDKDeparture\n")
            i = 0
            for router_list in in_routers:
                for router in router_list:
                    r_num = (int(re.search('[0-9]+', router).group(0)))
                    self.file_handler.write(
                        "out%d :: VLANEncap(${vlan%d}) -> ${out_if%d};\n"
                        % (r_num, r_num, r_num))
                    i = i + 1

        else:
            # FIX NON DPDK
            counter = 1
            for router in in_routers:
                self.file_handler.write(
                    "out%d :: ThreadSafeQueue() -> ToDevice(${if%d}, BURST 64);\n"
                    % (counter, int(re.search('[0-9]+', router).group(0))))
                counter = counter + 1
            for i in range(self.num_others):
                self.file_handler.write(
                    "out%d :: ThreadSafeQueue() -> ToDevice(${ifo%d}, BURST 64);\n"
                    % (counter, i + 1))
                counter = counter + 1

    def write_arp_handler(self):
        self.file_handler.write("\n// Handle arp\n")
        in_routers = list(nx.get_node_attributes(self.graph, 'in_routers').values())
        in_routers.sort(key=lambda x: int(re.search('[0-9]+', x[0]).group(0)))
        route_begin = 1
        for router_list in in_routers:
            route_begin = route_begin + len(router_list)

        self.file_handler.write("arpt :: Tee(%d);\n\n" % route_begin)
        i = 1
        # FIX HTIS TOO
        for router_list in in_routers:
            for router in router_list:
                counter = int(re.search('[0-9]+', router).group(0))
                if self.args.use_dpdk:
                    self.file_handler.write(
                        "c%d[1] -> ar%d :: ARPResponder(${if%d_ip} ${if%d_eth}) -> out%d;\n"
                        % (counter, counter, counter, counter, counter))
                    self.file_handler.write(
                        "arpq%d :: ARPQuerier(${if%d_ip}, ${if%d_eth}) -> out%d;\n"
                        % (counter, counter, counter, counter))
                else:
                    self.file_handler.write(
                        "c%d[1] -> ar%d :: ARPResponder(${if%d}:ip ${if%d}:eth) -> out%d;\n"
                        % (i, i, counter, counter, i))
                    self.file_handler.write(
                        "arpq%d :: ARPQuerier(${if%d}:ip, ${if%d}:eth) -> out%d;\n"
                        % (i, counter, counter, i))
                self.file_handler.write("c%d[2] -> arpt;\n" % counter)
                self.file_handler.write("arpt[%d] -> [1]arpq%d;\n\n" % (i - 1, counter))
                i = i + 1

        self.file_handler.write("chost[1] -> c1;\n")
        self.file_handler.write("chost[2] -> arpt;\n")

    def write_arp_less(self):
        self.file_handler.write("\n// Handle arpless\n")
        counter = 1
        second_counter = 1
        in_routers = list(nx.get_node_attributes(self.graph, 'in_routers').values())
        in_routers.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))
        for router in in_routers:
            if_n = int(re.search('[0-9]+', router).group(0))
            self.file_handler.write(
                "al%d :: EtherEncap(0x0800, ${if%d}:eth, ${if%d_friend})\n" %
                (counter, if_n, if_n))
            counter = counter + 1
            second_counter = second_counter + 1
        for i in range(self.num_others):
            counter = i + 1
            self.file_handler.write(
                "al%d :: EtherEncap(0x0800, ${ifo%d}:eth, ${ifo%d_friend})\n" %
                (second_counter, counter, counter))
            second_counter = second_counter + 1

    def write_drop_packers_on_routers(self):
        self.file_handler.write("\n// Send IP Packets to Routers\n")
        in_routers = nx.get_node_attributes(self.graph, 'in_routers')

        bandwidth = self.args.bw
        delay = self.args.delay
        drop = self.args.loss
        queue_length = 1000

        for router, router_list in in_routers.items():
            for router_iface in router_list:
                iface = int(re.search('[0-9]+', router_iface).group(0))
                if self.args.in_constraints:
                    # should check if we have overrides
                    self.file_handler.write(
                        "link_in_%d_queue :: ThreadSafeQueue(%d);\n" % (iface, queue_length))
                    self.file_handler.write(
                        "link_in_%d_bw :: LinkUnqueue(%s, %s);\n" % (iface, delay, bandwidth))
                    self.file_handler.write(
                        "link_in_%d_loss :: RandomSample(DROP %s);\n" % (iface, drop))

                    self.file_handler.write(
                        "c%d[0] -> Strip(14) -> CheckIPHeader(0) -> link_in_%d_queue -> CoDel() "
                        "-> link_in_%d_loss -> link_in_%d_bw -> router%s;\n"
                        % (iface, iface, iface, iface, router))
                else:
                    self.file_handler.write(
                        "c%d[0] -> Strip(14) -> CheckIPHeader(0) -> router%s;\n"
                        % (iface, router))
        self.file_handler.write(
            "chost[0] -> Strip(14) -> CheckIPHeader(0) -> router%d;\n" % (self.in_routers[0])
        )

    def write_routers_to_interfaces(self):
        in_routers = nx.get_node_attributes(self.graph, 'in_routers')
        num_inputs = len(in_routers)
        self.file_handler.write("\n// Send out packets to Interfaces\n")
        tmp_list = list(set(self.in_routers))

        bandwidth = self.args.bw
        delay = self.args.delay
        drop = self.args.loss
        queue_length = 1000

        for i in range(num_inputs):
            neighs = list(nx.all_neighbors(self.graph, str(tmp_list[i])))
            neighs.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))
            counter = 0
            for neigh in neighs:
                if re.match("[oe][0-9]+", neigh):
                    if not self.arp_less:
                        inputs = in_routers[str(tmp_list[i])]
                        iface = int(re.search('[0-9]+', inputs[counter]).group(0))
                        if self.args.in_constraints:
                            self.file_handler.write(
                                "link_out_%d_queue :: ThreadSafeQueue(%d);\n"
                                % (iface, queue_length)
                            )
                            self.file_handler.write(
                                "link_out_%d_bw :: LinkUnqueue(%s, %s);\n"
                                % (iface, delay, bandwidth)
                            )
                            self.file_handler.write(
                                "link_out_%d_loss :: RandomSample(DROP %s);\n" % (iface, drop)
                            )

                            self.file_handler.write(
                                "router%d[%d] -> r%dttl_out_%s -> link_out_%d_queue -> CoDel() "
                                "-> link_out_%d_loss -> link_out_%d_bw -> arpq%d;\n"
                                % (tmp_list[i], neighs.index(neigh), tmp_list[i], neigh,
                                   iface, iface, iface, iface))
                        else:
                            self.file_handler.write(
                                "router%d[%d] -> r%dttl_out_%s -> arpq%d;\n"
                                % (tmp_list[i], neighs.index(neigh), tmp_list[i], neigh,
                                   int(re.search('[0-9]+', inputs[counter]).group(0))))
                        counter = counter + 1
                    else:
                        # fix this later, see above
                        self.file_handler.write(
                            "router%d[%d] -> r%dttl_out_%s -> al%d -> out%d;\n"
                            % (self.in_routers[i], neighs.index(neigh),
                               self.in_routers[i], neigh, i + 1, i + 1))

    # pylint: disable=too-many-locals
    def write_link_shaping(self):
        self.file_handler.write("\n// Link Traffic Shaping\n")
        edges = nx.edges(self.graph)
        tees = nx.get_edge_attributes(self.graph, 'tee')
        bws = nx.get_edge_attributes(self.graph, 'bw')
        delays = nx.get_edge_attributes(self.graph, 'delay')
        drops = nx.get_edge_attributes(self.graph, 'drop')
        losses = nx.get_edge_attributes(self.graph, 'loss')
        pull_elements = nx.get_edge_attributes(self.graph, 'l_elements')
        push_elements = nx.get_edge_attributes(self.graph, 's_elements')
        for edge in edges:
            if re.match("[oe][0-9]+", edge[0]) or re.match("[oe][0-9]+", edge[1]):
                continue
            edge0 = int(edge[0])
            edge1 = int(edge[1])
            bandwidth = self.args.bw
            delay = self.args.delay
            drop = self.args.loss
            if edge in bws:
                bandwidth = bws[edge]
            if edge in delays:
                delay = delays[edge]
            if edge in drops:
                drop = drops[edge]
            elif edge in losses:
                drop = losses[edge]

            queue_length = 1000

            self.file_handler.write(
                "link_%d_%d_queue :: ThreadSafeQueue(%d);\n" % (edge0, edge1, queue_length)
            )
            self.file_handler.write(
                "link_%d_%d_bw :: LinkUnqueue(%s, %s);\n" % (edge0, edge1, delay, bandwidth)
            )
            self.file_handler.write(
                "link_%d_%d_loss :: RandomSample(DROP %s);\n" % (edge0, edge1, drop)
            )
            self.file_handler.write(
                "link_%d_%d_queue :: ThreadSafeQueue(%d);\n" % (edge1, edge0, queue_length)
            )
            self.file_handler.write(
                "link_%d_%d_bw :: LinkUnqueue(%s, %s);\n" % (edge1, edge0, delay, bandwidth)
            )
            self.file_handler.write(
                "link_%d_%d_loss :: RandomSample(DROP %s);\n" % (edge1, edge0, drop)
            )

            if edge in pull_elements:
                for element in pull_elements[edge]:
                    tokens = element.split('(')
                    element_short = get_capital_letters(tokens[0])
                    self.file_handler.write(
                        "link_%d_%d_%s :: %s;\n" % (edge0, edge1, element_short, element))
                    self.file_handler.write(
                        "link_%d_%d_%s :: %s;\n" % (edge1, edge0, element_short, element))

            if edge in push_elements:
                for element in push_elements[edge]:
                    tokens = element.split('(')
                    element_short = get_capital_letters(tokens[0])
                    self.file_handler.write(
                        "link_%d_%d_%s :: %s;\n" % (edge0, edge1, element_short, element))
                    self.file_handler.write(
                        "link_%d_%d_%s :: %s;\n" % (edge1, edge0, element_short, element))

            if edge in tees:
                self.file_handler.write("link_%d_%d_tee :: Tee(2);\n" % (edge0, edge1))
                self.file_handler.write("link_%d_%d_tee :: Tee(2);\n" % (edge1, edge0))

    def write_ttl_dec(self):
        self.file_handler.write("\n// Decrement TTL and send time exceeded replies\n")
        edges = nx.edges(self.graph)
        for edge in edges:
            if re.match("[oe][0-9]+", edge[0]) or re.match("[oe][0-9]+", edge[1]):
                if re.match("[oe][0-9]+", edge[0]):
                    out = edge[0]
                    edge = int(edge[1])
                else:
                    out = edge[1]
                    edge = int(edge[0])
                self.file_handler.write("r%dttl_out_%s :: DecIPTTL;\n" % (edge, out))
                self.file_handler.write(
                    "r%dttl_out_%s[1] -> ICMPError(10.100.150.%d, timeexceeded) -> router%d;\n"
                    % (edge, out, edge, edge))
            else:
                edge0 = int(edge[0])
                edge1 = int(edge[1])
                self.file_handler.write("r%dttl_%d :: DecIPTTL;\n" % (edge0, edge1))
                self.file_handler.write(
                    "r%dttl_%d[1] -> ICMPError(10.100.150.%d, timeexceeded) -> router%d;\n"
                    % (edge0, edge1, edge0, edge0)
                )
                self.file_handler.write("r%dttl_%d :: DecIPTTL;\n" % (edge1, edge0))
                self.file_handler.write(
                    "r%dttl_%d[1] -> ICMPError(10.100.150.%d, timeexceeded) -> router%d;\n"
                    % (edge1, edge0, edge1, edge1)
                )

    def write_routers(self):
        routes = nx.get_node_attributes(self.graph, 'routes')
        node_ips = nx.get_node_attributes(self.graph, 'ips')
        self.file_handler.write("\n// Routers\n")

        if __NX_VERSION__ > 1:
            nodes = list(nx.nodes(self.graph).keys())
        else:
            nodes = list(nx.nodes(self.graph))

        in_routers = nx.get_node_attributes(self.graph, 'in_routers')

        for node in nodes:
            if re.match("[oe][0-9]+", node):
                continue
            ifaces = routes[node]['ifaces']
            ips = routes[node]['ips']
            neighbors = list(nx.all_neighbors(self.graph, node))
            neighbors.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))
            first_str = "router%s :: RadixIPLookup(" % node
            last_str = ""
            middle_str = ""
            for iface, nhop in ifaces.items():
                if node in in_routers and iface in in_routers[node]:
                    last_str = "%s,\n                         ${%s_16} ${%s_gw} %d" % (
                        last_str, iface, iface, neighbors.index(nhop)
                    )
                    if self.args.use_dpdk:
                        middle_str = "${%s_ip} %d,\n                         %s" % (
                            iface, len(neighbors), middle_str
                        )
                    else:
                        middle_str = "${%s}:ip %d" % (iface, len(neighbors))

                else:
                    last_str = "%s,\n                         ${%s_16} %d" % (
                        last_str, iface, neighbors.index(nhop)
                    )
            for ip_addr, nhop in ips.items():
                last_str = "%s,\n                         %s %d" % (
                    last_str, ip_addr, neighbors.index(nhop)
                )
            last_str = "%s,\n                         %s %d" % (
                last_str, node_ips[node], len(neighbors)
            )
            last_str = "%s);\n\n" % last_str
            if middle_str == "":
                last_str = last_str[27:]
            else:
                middle_str = middle_str.strip(',\n ')
            self.file_handler.write(first_str)
            self.file_handler.write(middle_str)
            self.file_handler.write(last_str)

    def write_links(self):
        self.file_handler.write("\n// Links\n")
        if __NX_VERSION__ > 1:
            nodes = list(nx.nodes(self.graph).keys())
        else:
            nodes = list(nx.nodes(self.graph))
        nodes.sort()

        use_codel = self.args.use_codel

        for node in nodes:
            if re.match("[oe][0-9]+", node):
                continue
            neighbors = list(nx.all_neighbors(self.graph, node))
            neighbors.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))

            for neigh in neighbors:
                if re.match("[oe][0-9]+", neigh):
                    continue

                pull_elements = self.graph[node][neigh]['l_elements']
                push_elements = self.graph[node][neigh]['s_elements']

                push_str = "->"
                pull_str = "->"
                tee_str = "->"

                codel = "->"
                if use_codel:
                    codel = "-> CoDel() ->"

                for element in pull_elements:
                    tokens = element.split("(")
                    element_short = get_capital_letters(tokens[0])
                    pull_str = "%s link_%s_%s_%s ->" % (pull_str, node, neigh, element_short)

                for element in push_elements:
                    tokens = element.split("(")
                    element_short = get_capital_letters(tokens[0])
                    push_str = "%s link_%s_%s_%s ->" % (push_str, node, neigh, element_short)

                if 'tee' in self.graph[node][neigh]:
                    tee_str = "-> link_%s_%s_tee ->" % (node, neigh)

                self.file_handler.write(
                    "router%s[%d] -> r%sttl_%s %s SetTimestamp(FIRST true) -> link_%s_%s_queue "
                    "%s link_%s_%s_loss %s link_%s_%s_bw %s router%s\n"
                    % (node, neighbors.index(neigh), node, neigh, push_str, node, neigh,
                       codel, node, neigh, pull_str, node, neigh, tee_str, neigh))

    def write_teed_links(self):
        tees = nx.get_edge_attributes(self.graph, 'tee')
        self.file_handler.write("\n // Teed Inputs and Outputs\n")
        self.file_handler.write("\n // Input from Teed interfaces is discarded\n")
        counter = self.num_others + 1
        for edge in tees:
            self.file_handler.write("FromDevice(${ifo%d}) -> Discard;\n" % (counter))
            counter = counter + 1

        self.file_handler.write("\n// Output Chains\n")
        counter = self.num_others + 1
        k = self.num_inputs + 1

        for edge in tees:
            self.file_handler.write(
                "link_%s_%s_tee[1] -> al%d :: EtherEncap(0x0800, ${ifo%d}:eth, ${ifo%d_friend})\n"
                % (edge[0], edge[1], k, counter, counter))
            self.file_handler.write("link_%s_%s_tee[1] -> al%d;\n" % (edge[1], edge[0], k))
            counter = counter + 1
            k = k + 1

        k = self.num_inputs + 1
        counter = self.num_others + 1

        for edge in tees:
            self.file_handler.write(
                "al%d -> ThreadSafeQueue() -> ToDevice(${ifo%d});\n" %
                (k, counter))
            k = k + 1
            counter = counter + 1

    def write_local_delivery(self):
        self.file_handler.write("\n// Local Delivery\n")
        if self.args.use_dpdk:
            self.file_handler.write("toh :: ToHost(fakedge0);\n\n")
        else:
            self.file_handler.write("toh :: ToHost;\n\n")
        if __NX_VERSION__ > 1:
            routers = list(nx.nodes(self.graph).keys())
        else:
            routers = list(nx.nodes(self.graph))
        for router in routers:
            if not re.match("[oe][0-9]+", router):
                neighbors = list(nx.all_neighbors(self.graph, str(router)))
                self.file_handler.write(
                    "router%s[%d] -> EtherEncap(0x0800, 1:1:1:1:1:1, 2:2:2:2:2:2) -> toh;\n"
                    % (router, len(neighbors)))

        if not self.arp_less:
            self.file_handler.write("arpt[%d] -> toh;\n" % len(self.in_routers))
        else:
            for router in self.in_routers:
                pos = self.in_routers.index(router) + 1
                self.file_handler.write("c%d[1] -> toh;\n" % pos)
                self.file_handler.write("c%d[2] -> toh;\n" % pos)
            self.file_handler.write("chost[1] -> Discard;\n")
            self.file_handler.write("chost[2] -> Discard;\n")

        self.file_handler.write("\n// Unknown packets to their death\n")
        in_rtr = list(nx.get_node_attributes(self.graph, 'in_routers').values())
        in_rtr.sort(key=lambda x: int(re.search('[0-9]+', x[0]).group(0)))
        for router_list in in_rtr:
            for router in router_list:
                pos = int(re.search('[0-9]+', router).group(0))
                self.file_handler.write(
                    "c%d[3] -> Print(\"${if%d} Non IP\") -> Discard;\n"
                    % (pos, pos))

        self.file_handler.write("chost[3] -> Print(\"Host Non IP\") -> Discard;\n")
