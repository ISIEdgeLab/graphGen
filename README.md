# GraphGen
=======

[![Build Status](https://travis-ci.org/ISIEdgeLab/graphGen.svg?branch=master)](https://travis-ci.org/ISIEdgeLab/graphGen)

GraphGen is a framework for creating virtual topologies through the click modular router in deterlab (https://www.isi.deterlab.net).  It has multiple components, but the main two are the topology generation through `graphGen/ns_gen.py` which generates an ns2/tcl file describing the devices, operating systems, link components, etc.  The second component is `graphGen/click_gen.py` which is responsible for generating click's virtual router template (default: vrouter.template) that is plugged into click to implement the network components of the topology.

GraphGen is written in python and is under active development, please feel free to contribute by submitting a pull request.  Our coding standards are described in .pylintrc and setup.cfg, and the set of tests current implemented is shown in .travis.yml.  The code should be capable of being run in python 2 and python 3 environments.
