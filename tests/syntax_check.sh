#!/bin/bash

if [ "$1" == "" ]; then
    echo "usage: $0 nsfile.ns"
    exit 1
fi

cpwd=$(pwd)
nagel=nagelfar

cd "$cpwd/$nagel"
"$cpwd/$nagel/emulab_checker.sh" "$cpwd/$1"
retcode=$?
cd $cpwd

exit $retcode
