#!/usr/bin/env bash

# Bash and Dash compatible.

TEMPLATE_DIR=/proj/edgect/templates/
BURST=0

if test $# -eq 0; then
	echo "ERROR: Not enough arguments given."
	"$0" -h
	exit 1
fi

TEMPLATE_GIVEN=false
ARGS="$@"

while test $# -gt 0; do
	case "$1" in
		-h|--help)
			echo "$0: Install necessary packages, configure click and start DPDK click"
			echo "Usage: $0 [-p|--path path_to_templates] template_name"
			echo -e "\t-h, --help\tProduce this help message and exit."
			echo -e "\t-p, --path\tLook for Click  templates in this directory."
			echo -e "\t\t\tWithout this option, script will search for templates in ${TEMPLATE_DIR}"
			echo -e "\t-b, --burst\tProvide a burst parameter to DPDK."
			echo -e "\t\t\tAllows controlling number of packets to send to the NIC."
			exit 0
			;;
		-p|--path)
			shift
			if test $# -gt 0; then
				TEMPLATE_DIR=$1
			else
				echo "ERROR: No path given to -p|--path option"
				exit 1
			fi
			shift
			;;
		-b|--burst)
			shift
			if test $# -gt 0; then
				BURST=$1
			else
				echo "ERROR: No burst value provided"
				exit 1
			fi
			shift
			;;
		*)
			if $TEMPLATE_GIVEN; then
				echo "ERROR: Given multiple templates?"
				"$0" -h
				exit 1
			fi
			TEMPLATE_GIVEN=true
			TEMPLATE=$1
			shift						
			;;
	esac
done

if ! $TEMPLATE_GIVEN; then
	echo "ERROR: No template given."
	exit 1
fi

if [ ! -d "$TEMPLATE_DIR" ]; then
	echo "ERROR: No such directory: \"$TEMPLATE_DIR\""
	exit 1
fi

if [ ! -d "$TEMPLATE_DIR/$TEMPLATE" ]; then
	echo "ERROR: No such template directory found: \"$TEMPLATE_DIR/$TEMPLATE\""
	exit 1
fi

if [ ! -f "$TEMPLATE_DIR/$TEMPLATE/vrouter.template" ]; then
	echo "ERROR: Click template ($TEMPLATE_DIR/$TEMPLATE/vrouter.template) not found."
	exit 1
fi

echo "INFO: Given template $TEMPLATE and dir $TEMPLATE_DIR"

# If we weren't given permission, we're taking it anyway! 
# BAD!, but hey, our script is a special snowflake.
# (Check if we're running with the right privs, and if not, try running ourselves again with perms.)
# (Do dash compliant $EUID check)
if [ `id -u`  -ne 0 ]; then
	echo "INFO: Rerunning script with sudo privs."
	echo "sudo $0 $ARGS"
	exec sudo "$0" $ARGS
fi

apt-get update
apt-get install python-netaddr python-netifaces -y;

cp $TEMPLATE_DIR/$TEMPLATE/vrouter.template /tmp
python /proj/edgect/exp_scripts/updateClickConfig.py --burst $BURST

# Kill possibly lingering instances. 
# If we end up killing click, we need to wait for clean up or we can't start a new click.
# (e.g. without the pause, starting click will fail and we can't run this script back-to-back)
KILL_COUNT=`pkill --euid 0 -c click`
if [ $KILL_COUNT -gt 0 ]; then
	echo "INFO: Killed $KILL_COUNT click processes"
	# Hack - surely a better way:
	sleep 5
fi
rm -f /click

click --dpdk -c 0xffffff -n 4 -- -u /click /tmp/vrouter.click >/tmp/click.log 2>1 < /dev/null &






