# pylint: disable=invalid-name
'''
    ns_gen.py generates a NS file associated with the given graph file.
    The file generated will "enclaves" with ct, crypto, traffic and server boxes.
'''

import re
import time
import networkx as nx
__NX_VERSION__ = int(nx.__version__.split('.')[0])


# pylint: disable=too-many-instance-attributes
class NSGen(object):
    ''' responsible for configuring network simulator topology file '''
    def __init__(self, args):
        self.g = None
        self.args = args
        self.use_dpdk = False
        self.use_crypto = False
        self.num_servers = -1
        self.num_clients = -1
        self.num_external = -1
        self.enclaves = -1
        self.num_enclaves = -1
        self.num_tees = -1

    def set_graph(self, g):
        ''' set NSGen's the networkx graph '''
        self.g = g

    # input: str, returns -> None
    # remove any need to worry about race conditions or fd handling
    def writeToFile(self, file_contents):
        ''' single function responsible to writing to files '''
        file_name = self.args.ns_file
        with open(file_name, 'a') as fi:
            fi.write(file_contents)

    def writeNS(self):
        ''' clear previous contents, as writes are done via appends '''
        # first time we call this function, delete previous copy
        with open(self.args.ns_file, 'w'):
            pass

        # dangerous syntax, need to use with or reduce use
        self.use_dpdk = self.args.use_dpdk

        # Determine number of servers and clients per enclave
        self.num_servers = int(self.args.num_servers)
        self.num_clients = int(self.args.num_clients)

        # Determine number of External (non Enclave) nodes
        self.num_external = len(nx.get_node_attributes(self.g, 'external'))
        self.enclaves = list(nx.get_node_attributes(self.g, 'enclaves'))
        self.enclaves.sort(key=lambda x: int(re.search('[0-9]+', x).group(0)))

        # Determine total enclaves based on number of specified interfaces for the vrouter
        # need to subtract out external nodes
        self.num_enclaves = len(nx.get_node_attributes(self.g, 'ifs')) - self.num_external
        self.num_tees = len(nx.get_edge_attributes(self.g, 'tee'))
        self.use_crypto = self.args.use_crypto

        # Determine base directory where to search files
        self.base_directory = self.args.base_directory

        self.writePreamble(self.args.start_cmd)
        lans = self.writeEnclaveNodes(self.args.os, self.args.ct_os)
        self.writeExternalNodes()
        self.writeLansLinks(lans)
        self.writeIPs()
        self.writeTeeNodes(self.args.os)

        if self.args.use_containers:
            self.writeContainers()

        self.writeStartCmds()
        self.writeEpilogue()

    def writePreamble(self, start_cmd):
        ''' This function writes the NS preamble, as well as setting up start command strings'''
        ns_file_name = self.args.ns_file.split('.')[0]
        magi_location = self.base_directory + 'magi/current'
        edge_scripts = self.base_directory + 'exp_scripts'

        self.writeToFile(
            '# Autogenerated by ns_gen.py - {time} UTC\n'
            'set ns [new Simulator]\n'
            'source tb_compat.tcl\n\n'
            'set magi_str "sudo python {magi}/magi_bootstrap.py -fp {magi}/"\n\n'
            'set click_str "{scripts_dir}/{click_script} {ns_file}"\n'.format(
                time=time.asctime(time.gmtime(time.time())),
                magi=magi_location,
                scripts_dir=edge_scripts,
                click_script='startClickDPDK.sh' if self.use_dpdk else 'startClickAny.sh',
                ns_file=ns_file_name,
            )
        )

        if self.args.write_routes:
            self.writeToFile(
                '\nset ct_str "{scripts_dir}/{route_script} {ns_file}"\n'.format(
                    scripts_dir=edge_scripts,
                    ns_file=ns_file_name,
                    route_script='updateRoutesAny.sh',
                )
            )

        # Always have a basic my_start regardless of user definition
        self.writeToFile(
            '\nset my_start "{cmd}"\n'.format(
                cmd=start_cmd if start_cmd else 'touch /tmp/my_start',
            )
        )

        # pylint: disable=fixme
        # FIXME: erik - how do we want this to behave for the user?
        # currently the implementation below makes no sense because it will
        # cause/allow many nodes to choose from the available list of hardware
        # devices, even if it isnt the one specified.
        # Furthermore, if a bandwidth specification is given (10Gbps) with
        # a specified hardware, how will deter meet the requirements.
        # unfortuneately, it leads me to think this script is not helpful as
        # deter may reject a topology given.
        if not self.args.use_containers:
            self.writeToFile(
                '\n# Create hardware types\n'
                'tb-make-soft-vtype click_hardware {{{click_hardware} {opt_modules}}}\n'
                'tb-make-soft-vtype ct_hardware {{{ct_hardware} {opt_modules}}}\n'
                'tb-make-soft-vtype crypto_hardware {{{crypto_hardware} {opt_modules}}}\n'
                'tb-make-soft-vtype client_hardware {{{client_hardware} {opt_modules}}}\n'.format(
                    client_hardware=self.args.clientHardware,
                    crypto_hardware=self.args.cryptoHardware,
                    click_hardware=self.args.clickHardware,
                    opt_modules='sm ' if self.use_dpdk else '' + 'dl380g3 MicroCloud',
                    ct_hardware=self.args.ctHardware,
                )
            )

    def writeEnclaveNodes(self, os, ct_os):
        '''
            Write the enclave nodes, providing the specified os, number of server
            and number of clients per enclave
        '''

        # We build up the LAN string as we go to save time later
        lan_strs = []
        enclave_write_str = '\n# Enclaves\n'
        for enclave in self.enclaves:
            enc_number = int(re.search('[0-9]+', enclave).group(0))
            enclave_write_str += '\n# Enclave %d\n' % enc_number

            # Legacy BLAH.  If number of servers per enclave is 1, don_t add a server number
            lstr = 'ct%d' % enc_number
            for server_number in range(1, self.num_servers + 1):
                lstr += ' server{enclave_value}{server_value}'.format(
                    enclave_value=enc_number,
                    server_value=server_number if server_number > 1 else "",
                )
                enclave_write_str += \
                    'set server{enclave_value}{server_value} [$ns node]\n' \
                    'tb-set-hardware $server{enclave_value}{server_value} {client_hw}\n'.format(
                        enclave_value=enc_number,
                        server_value=server_number if server_number > 1 else "",
                        client_hw=self.args.client_hardware
                    )
                if not self.args.use_containers:
                    enclave_write_str += \
                        'tb-set-node-os $server{enclave_value}{server_value} {client_os}\n'.format(
                            enclave_value=enc_number,
                            server_value=server_number if server_number > 1 else "",
                            client_os=os,
                        )

            # Write Client nodes
            # lincoln: if deter okay with ns, we could move this up above and template server/traf
            for client_number in range(1, self.num_clients + 1):
                enclave_write_str += \
                    'set traf{enclave_value}{client_value} [$ns node]\n' \
                    'tb-set-hardware $traf{enclave_value}{client_value} {client_hw}\n'.format(
                        enclave_value=enc_number,
                        client_value=client_number,
                        client_hw=self.args.client_hardware
                    )
                lstr += ' traf%d%d' % (enc_number, client_number)
                if not self.args.use_containers:
                    enclave_write_str += \
                        'tb-set-node-os $traf{enclave_value}{client_value} {client_os}\n'.format(
                            enclave_value=enc_number,
                            client_value=client_number if client_number > 1 else "",
                            client_os=os,
                        )

            # Write CT and Crypto nodes
            enclave_write_str += \
                'set ct{enclave_value} [$ns node]\n' \
                'tb-set-node-os $ct{enclave_value} {ct_os}\n' \
                'tb-set-hardware $ct{enclave_value} {ct_hardware}\n'.format(
                    enclave_value=enc_number,
                    ct_os=ct_os,
                    ct_hardware=self.args.ct_hardware,
                )

            if __NX_VERSION__ > 1:
                neighbors = [y for y in self.g.neighbors(enclave)]
            else:
                neighbors = self.g.neighbors(enclave)
            if self.use_crypto:
                enc_neigh_len = len(neighbors)
                for neigh_number in range(1, enc_neigh_len + 1):
                    enclave_write_str += \
                        'set crypto{enclave_value}{neigh_value} [$ns node]\n' \
                        'tb-set-node-os ${{crypto{enclave_value}{neigh_value}}} {client_os}\n' \
                        'tb-set-hardware ${{crypto{enclave_value}{neigh_value}}} ' \
                        '{crypto_hardware}\n'.format(
                            enclave_value=enc_number,
                            neigh_value="-%s" % neigh_number if enc_neigh_len > 1 else "",
                            crypto_hardware=self.args.crypto_hardware,
                            client_os=os,
                        )
            lan_strs.append(lstr)

        # Write the control node and vrouter node
        enclave_write_str += \
            '\nset vrouter [$ns node]\n' \
            'tb-set-node-os $vrouter {dpdk_enabled_os}\n' \
            'tb-set-hardware $vrouter {click_hardware}\n' \
            'set control [$ns node]\n' \
            'tb-set-node-os $control {control_os}\n' \
            'tb-set-hardware $control {control_hardware}\n'.format(
                control_os=os,
                control_hardware=self.args.client_hardware,
                click_hardware=self.args.click_hardware,
                dpdk_enabled_os='Ubuntu1604-STD' if self.use_dpdk else 'Ubuntu1204-64-CT-CL2',
            )
        self.writeToFile(enclave_write_str)
        return lan_strs

    def writeExternalNodes(self):
        ''' Write any external nodes for this experiment '''

        self.writeToFile("\n# External Nodes\n")
        str_to_write = ''
        for extern_node in range(1, self.num_external + 1):
            str_to_write += 'set ext{extern_number} [$ns node]\n' \
                'tb-set-node-os $ext{extern_number} {node_os}\n' \
                'tb-set-hardware $ext{extern_number} {clientHW}\n'.format(
                    extern_number=extern_node,
                    node_os=self.args.os,
                    clientHW=self.args.clientHardware
                )
        self.writeToFile(str_to_write)

    # pylint: disable=too-many-locals
    def writeLansLinks(self, lans):
        ''' write lan configuration to ns file '''
        self.writeToFile('\n# Lans\n')
        link_str = ''
        elink_str = ''
        multiplex_str = ''
        default_bw = self.args.bw[:-2]  # strips ps from Mbps
        default_delay = self.args.delay
        # if edge is already assigned value, prefer over default value
        bws = nx.get_edge_attributes(self.g, 'bw')
        delays = nx.get_edge_attributes(self.g, 'delay')

        str_to_write = ''
        enclaves = nx.get_node_attributes(self.g, 'enclaves')
        # Write the LANs for each enclave, as well as the ct-crypto link and crpyto-vrouter links
        enclaveNumbers = [int(re.search('[0-9]+', enclave).group(0)) for enclave in enclaves]
        enclaveNumbers.sort()
        for lan, lan_number in zip(lans, enclaveNumbers):
            str_to_write += \
                'set lan{lan_value} [$ns make-lan "{lan_name}" {bandwidth} {delay}]\n'.format(
                    lan_value=lan_number,
                    lan_name=lan,
                    bandwidth=default_bw,
                    delay=default_delay,
                )
            enclave = enclaves['e{}'.format(lan_number)]
            if __NX_VERSION__ > 1:
                neighbors = [y for y in self.g.neighbors(enclave)]
            else:
                neighbors = self.g.neighbors(enclave)
            for neighbor, neighbor_num in zip(neighbors, enumerate(neighbors)):
                # shouldnt need sorting here since enclave starts with 'e'
                edge = (neighbor, enclave)
                edgeInBW = bws.get(edge, default_bw)
                edgeInDelay = delays.get(edge, default_delay)
                lan_value = str(lan_number) + '-' + str(neighbor_num[0]) \
                    if len(neighbors) > 1 else str(lan_number)
                if self.use_crypto:
                    link_str = '{prefix_str}set link{lan_value} [$ns duplex-link $ct{lan_number} ' \
                        '${{crypto{lan_value}}} {bandwidth} {delay} DropTail]\n'.format(
                            prefix_str=link_str,
                            lan_number=lan_number,
                            lan_value=lan_value,
                            bandwidth=edgeInBW,
                            delay=edgeInDelay,
                        )
                elink_str = '{prefix_str}set elink{lan_value} [$ns duplex-link ' \
                    '${device_type} $vrouter {bandwidth} {delay} DropTail]\n'.format(
                        prefix_str=elink_str,
                        device_type='crypto%s' % lan_value
                        if self.use_crypto else 'ct%d' % lan_number,
                        lan_value=lan_value,
                        bandwidth=edgeInBW,
                        delay=edgeInDelay,
                    )
                multiplex_str = '{prefix_str}tb-set-multiplexed ${{elink{lan_value}}} 1\n' \
                    'tb-set-noshaping ${{elink{lan_value}}} 1\n'.format(
                        prefix_str=multiplex_str,
                        lan_value=lan_value,
                    )

        # I (ek) try to bunch everything in the output file together for easy reading.
        # Thats why all the link_strs and elink_strs are grouped together
        str_to_write += \
            '\n# Internal Links\n{ilinks}' \
            '\n# Egress Links\n{elinks}' \
            '\ntb-set-vlink-emulation "vlan"\n{mlinks}'.format(
                ilinks=link_str,
                elinks=elink_str,
                mlinks=multiplex_str,
            )

        # Write External Links
        str_to_write += '\n# External Node Links\n'
        for extern_nodes in range(1, self.num_external + 1):
            str_to_write += \
                'set olink{0} [$ns duplex-link $vrouter $ext{0} {1} {2} DropTail]\n'.format(
                    extern_nodes, default_bw, default_delay,
                )
            str_to_write += \
                'tb-set-multiplexed $olink{0} 1\ntb-set-noshaping $olink{0}\n'.format(
                    extern_nodes,
                )
        self.writeToFile(str_to_write)

    def writeIPs(self):
        ''' write out ip section, beware, more than 99 enclaves will break topo '''
        # Enumerate and write the Enclave IPs.  Enclaves are given /16's.  Thus enclave 1 is
        # 10.1.0.0/16 etc...  10.100 is reserved for internal use.  If we ever have more than 99
        # enclaves, we'll have to deal.

        enclave_ip_str = '\n# IPS\n'
        egress_str = '\n# Egress link IPS\n'
        ifs = nx.get_node_attributes(self.g, 'ifs')
        for enclave in self.enclaves:
            if __NX_VERSION__ > 1:
                neighbors = [y for y in self.g.neighbors(enclave)]
            else:
                neighbors = self.g.neighbors(enclave)
            enclave_neigh_len = len(neighbors)
            enclave_number = int(re.search('[0-9]+', enclave).group(0))
            enclave_ip_str += '\n# IPs for Enclave %d\n' % enclave_number

            for client_number in range(1, self.num_clients + 1):
                enclave_ip_str += 'tb-set-ip-lan $traf{enclave}{client} $lan{enclave} ' \
                    '10.{enclave}.1.{client}\n'.format(
                        enclave=enclave_number,
                        client=client_number,
                    )
            # server's ips start at max client number
            begin_server_addr = self.num_clients
            for server_number in range(1, self.num_servers + 1):
                enclave_ip_str += 'tb-set-ip-lan $server{enclave}{opt_server} ' \
                    '$lan{enclave} 10.{enclave}.1.{server_addr}\n'.format(
                        enclave=enclave_number,
                        opt_server=server_number if self.num_servers > 1 else '',
                        server_addr=begin_server_addr + server_number,
                    )

            enclave_ip_str += 'tb-set-ip-lan $ct{enclave} $lan{enclave} ' \
                '10.{enclave}.1.100\n'.format(
                    enclave=enclave_number,
                )

            if self.use_crypto:
                for neighbors in range(enclave_neigh_len):
                    re_enclave = int(re.search('[0-9]+', ifs[enclave][neighbors]).group(0))
                    enclave_ip_str += 'tb-set-ip-link $ct{ct_device} ${{link{link_str}}} ' \
                        '10.{enclave}.2.1\n'.format(
                            enclave=enclave_number,
                            ct_device=enclave_number + '-' + neighbors
                            if enclave_neigh_len > 1 else enclave_number,
                            link_str=re_enclave,
                        )
                    enclave_ip_str += 'tb-set-ip-link ${{crypto{crypto_device}}} ' \
                        '${{link{link_str}}} 10.{crypto_net}.2.2\n'.format(
                            crypto_device=enclave_number + '-' + neighbors
                            if enclave_neigh_len > 1 else enclave_number,
                            link_str=enclave_number + '-' + neighbors
                            if enclave_neigh_len > 1 else enclave_number,
                            crypto_net=re_enclave,
                        )

            # not sure why this section forces to str() while others dont...
            enclave_number = int(re.search('[0-9]+', enclave).group(0))
            for neighbors in range(enclave_neigh_len):
                re_enclave = int(re.search('[0-9]+', ifs[enclave][neighbors]).group(0))
                if self.use_crypto:
                    egress_str += 'tb-set-ip-link ${{crypto{crypto_device}}} ' \
                        '${{elink{elink_name}}} 10.{re_enclave}.10.1\n'.format(
                            crypto_device=str(enclave_number) + '-' + str(neighbors)
                            if enclave_neigh_len > 1 else str(enclave_number),
                            elink_name=str(enclave_number) + '-' + str(neighbors)
                            if enclave_neigh_len > 1 else str(enclave_number),
                            re_enclave=re_enclave,
                        )
                    egress_str += 'tb-set-ip-link $vrouter ${{elink{elink_name}}} ' \
                        '10.{re_enclave}.10.2\n'.format(
                            elink_name=str(enclave_number) + '-' + str(neighbors)
                            if enclave_neigh_len > 1 else str(enclave_number),
                            re_enclave=re_enclave,
                        )
                else:
                    egress_str += 'tb-set-ip-link $ct{enclave_value} ${{elink{elink_name}}} '\
                        '10.{re_enclave}.2.1\n'.format(
                            elink_name=str(enclave_number) + '-' + str(neighbors)
                            if enclave_neigh_len > 1 else str(enclave_number),
                            re_enclave=re_enclave,
                            enclave_value=enclave_number,
                        )
                    egress_str += 'tb-set-ip-link $vrouter ${{elink{elink_name}}} ' \
                        '10.{re_enclave}.2.2\n'.format(
                            elink_name=str(enclave_number) + '-' + str(neighbors)
                            if enclave_neigh_len > 1 else str(enclave_number),
                            re_enclave=re_enclave,
                        )

        # External Links are using the 10.100.X\24s.  We use the 10.100.150\24 for
        # internal vrouter routing.  If we ever have more than 149 external nodes, we'll
        # have to deal.

        external_str = '\n# External Node Link IPS \n'
        for external in range(1, self.num_external + 1):
            external_str += 'tb-set-ip-link $ext{ext} $olink{ext} 10.100.{ext}.1\n'.format(
                ext=external,
            )
            external_str += 'tb-set-ip-link $vrouter $olink{ext} 10.100.{ext}.2\n'.format(
                ext=external,
            )

        self.writeToFile(enclave_ip_str + egress_str + external_str)

    # pylint: disable=too-many-branches
    def writeContainers(self):
        ''' write container section to ns file '''
        str_to_write = '\n# Container Partitioning\n'

        # All clients and servers in an enclave are placed in the same partition
        # Make this an option?

        for enclave in self.enclaves:
            enc_number = int(re.search('[0-9]+', enclave).group(0))
            for client_number in range(1, self.num_clients + 1):
                str_to_write += 'tb-add-node-attribute $traf{enclave_value}{client_value} ' \
                    'containers:partition {enclave_value}\n'.format(
                        enclave_value=enc_number,
                        client_value=client_number,
                    )
            for server_number in range(self.num_servers):
                str_to_write += 'tb-add-node-attribute $server{enclave_value}{opt_server} ' \
                    'containers:partition {enclave_value}\n'.format(
                        enclave_value=enc_number,
                        opt_server=server_number if self.num_servers > 1 else '',
                    )

        partition_value = len(self.enclaves) + 1
        # Everything is its own partition/embedded pnode.  Is this right way to do this?
        # More options?

        str_to_write += '\n'
        for enclave in self.enclaves:
            enc_number = int(re.search('[0-9]+', enclave).group(0))
            str_to_write += 'tb-add-node-attribute $ct{enclave_value} ' \
                'containers:partition {parition}\n'.format(
                    enclave_value=enc_number,
                    parition=partition_value,
                )

            partition_value += 1

            if __NX_VERSION__ > 1:
                neighbors = [y for y in self.g.neighbors(enclave)]
            else:
                neighbors = self.g.neighbors(enclave)

            if self.use_crypto:
                for neighbor_number in enumerate(neighbors):
                    str_to_write += 'tb-add-node-attribute ${{crypto{crypto_device}}} ' \
                        'containers:partition {partition}\n'.format(
                            crypto_device=enc_number + '-' + str(int(neighbor_number + 1))
                            if len(neighbors) > 1 else enc_number,
                            partition=partition_value,
                        )
                    partition_value += 1

        for external_number in range(self.num_external):
            str_to_write += 'tb-add-node-attribute $ext{external} ' \
                'containers:partition {partition}\n'.format(
                    external=external_number,
                    partition=partition_value,
                )
            partition_value += 1

        for tee_number in range(self.num_tees):
            str_to_write += 'tb-add-node-attribute $tee{tee_value} ' \
                'containers:partition {partition}\n'.format(
                    tee_value=tee_number,
                    partition=partition_value,
                )
            partition_value += 1

        str_to_write += '\n'
        str_to_write += 'tb-add-node-attribute $vrouter containers:partition {partition}\n'.format(
            partition=partition_value,
        )
        partition_value += 1
        str_to_write += 'tb-add-node-attribute $control containers:partition {partition}\n'.format(
            partition=partition_value,
        )

        str_to_write += '\n# Embed Physical Nodes\n'
        for enclave in self.enclaves:
            enc_number = int(re.search('[0-9]+', enclave).group(0))
            str_to_write += 'tb-add-node-attribute $ct{enclave_value} ' \
                'containers:node_type embedded_pnode\n'.format(
                    enclave_value=enc_number,
                )
            if self.use_crypto:
                for neighbor_number in enumerate(neighbors):
                    str_to_write += 'tb-add-node-attribute ${{crypto{crypto_device}}} ' \
                        'containers:node_type embedded_pnode\n'.format(
                            crypto_device=enc_number + '-' + str(int(neighbor_number + 1))
                            if len(neighbors) > 1 else enc_number,
                        )

        # External nodes could possibly be containerized.  Have to consider this!

        for external_number in range(1, self.num_external + 1):
            str_to_write += 'tb-add-node-attribute $ext{external} ' \
                'containers:node_type embedded_pnode\n'.format(
                    external=external_number,
                )

        for tee_number in range(1, self.num_tees + 1):
            str_to_write += 'tb-add-node-attribute $tee{tee_value} ' \
                ' containers:node_type embedded_pnode\n'.format(
                    tee_value=tee_number,
                )

        str_to_write += '\ntb-add-node-attribute $vrouter containers:node_type embedded_pnode\n'
        str_to_write += 'tb-add-node-attribute $control containers:node_type embedded_pnode\n'
        self.writeToFile(str_to_write)

    def writeStartCmds(self):
        ''' write start commands to ns file '''
        str_to_write = '\n# Start Commands\n'
        for enclave in self.enclaves:
            if __NX_VERSION__ > 1:
                neighbors = [y for y in self.g.neighbors(enclave)]
            else:
                neighbors = self.g.neighbors(enclave)
            enc_number = int(re.search('[0-9]+', enclave).group(0))
            str_to_write += '\n'
            for client_number in range(1, self.num_clients + 1):
                str_to_write += 'tb-set-node-startcmd $traf{enclave}{client} '\
                    '"$my_start; $magi_str"\n'.format(
                        enclave=enc_number,
                        client=client_number,
                    )
            for server_number in range(1, self.num_servers + 1):
                str_to_write += 'tb-set-node-startcmd $server{enclave}{opt_server} ' \
                    '"$my_start; $magi_str"\n'.format(
                        enclave=enc_number,
                        opt_server=server_number if self.num_servers > 1 else '',
                    )

            str_to_write += 'tb-set-node-startcmd $ct{enclave} ' \
                '"$my_start; {if_write_route}$magi_str"\n'.format(
                    enclave=enc_number,
                    if_write_route='$ct_str; ' if self.args.write_routes else '',
                )

            if self.use_crypto:
                for neighbor_number in enumerate(neighbors):
                    str_to_write += 'tb-set-node-startcmd ${{crypto{crypto_device}}} ' \
                        '"$my_start; $magi_str"\n'.format(
                            crypto_device=enc_number + '-' + str(int(neighbor_number + 1))
                            if len(neighbors) > 1 else enc_number,
                        )

        for external_number in range(self.num_external):
            str_to_write += 'tb-set-node-startcmd $ext{extern} "$my_start; $magi_str"\n'.format(
                extern=external_number,
            )

        str_to_write += '\ntb-set-node-startcmd $vrouter "$click_str; $my_start; $magi_str"\n'
        str_to_write += 'tb-set-node-startcmd $control "sudo python ' \
            + self.base_directory + 'exp_scripts/fixHosts.py; $my_start; $magi_str"\n'
        self.writeToFile(str_to_write)

    def writeTeeNodes(self, os):
        ''' write out tee nodes to ns file '''
        str_to_write = '\n# Write Tee Nodes\n'
        tees = nx.get_edge_attributes(self.g, 'tee')
        const_begin_range = 1
        const_begin_subnet_range = 151
        for edge in enumerate(tees):
            str_to_write += 'set tee{tvalue} [$ns node]\n'.format(
                tvalue=const_begin_range + edge
            )
            str_to_write += 'tb-set-node-os $tee{tvalue} {os_choice}\n'.format(
                tvalue=const_begin_range + edge,
                os_choice=os,
            )
            str_to_write += 'tb-set-node-startcmd $tee{tvalue} "$my_start; $magi_str"\n'.format(
                tvalue=const_begin_range + edge,
            )
            str_to_write += 'tb-set-hardware $tee{tvalue} cli_server_type\n'.format(
                tvalue=const_begin_range + edge,
            )
            str_to_write += 'set tlink{tvalue} [$ns duplex-link $vrouter $tee{tvalue} ' \
                '1000Mb 0.0ms DropTail]\n'.format(
                    tvalue=const_begin_range + edge,
                )
            str_to_write += 'tb-set-ip-link $tee{tvalue} $tlink{tvalue} 10.100.{subnet}.1\n'.format(
                tvalue=const_begin_range + edge,
                subnet=const_begin_subnet_range + edge,
            )
            str_to_write += 'tb-set-ip-link $vrouter $tlink{tvalue} 10.100.{subnet}.2\n'.format(
                tvalue=const_begin_range + edge,
                subnet=const_begin_subnet_range + edge,
            )
            str_to_write += 'tb-set-multiplexed $tlink{tvalue} 1\n' \
                'tb-set-noshaping $tlink{tvalue}\n'.format(
                    tvalue=const_begin_range + edge,
                )
        self.writeToFile(str_to_write)

    def writeEpilogue(self):
        ''' write the end of the ns file - define routing'''
        self.writeToFile(
            '\n# Epilogue\n'
            '$ns rtproto Static\n'
            '$ns run\n'
        )
