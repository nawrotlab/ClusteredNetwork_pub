#!/bin/bash
usage()
{
    echo "usage: Download.sh options:<e>"
    echo "-e     Download only experimental data"
}

exp_only=0
no_args="true"
while getopts 'e' option; do
    case $option in
        e)
            exp_only=1;;
        *)
            usage
            exit 1
    esac
    no_args="false"
done

if [ ! -d data ]; then
    mkdir data
else
    if [ "$(ls -A data)" ]; then
        read -p "The data folder is not empty. Do you want to overwrite it? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf data
            mkdir data
        else
            exit 1
        fi
    fi
fi

cd data
if [ ! -d experimental_data ]; then
    mkdir experimental_data
else
    if [ "$(ls -A experimental_data)" ]; then
        read -p "The experimental data folder is not empty. Do you want to overwrite it? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf experimental_data
            mkdir experimental_data
        else
            exit 1
        fi
    fi
fi
cd ../



# create tmp folder to store the downloaded files
if [ ! -d tmp ]; then
    mkdir tmp
fi
cd tmp

git clone https://gin.g-node.org/nawrotlab/delayed_center-out_uncertainty_Riehle
cd delayed_center-out_uncertainty_Riehle/pickle
mv * ../../../data/experimental_data
cd ../../../
rm -rf delayed_center-out_uncertainty_Riehle


if [ $exp_only -eq 0 ]; then
    cd tmp
    git clone https://gin.g-node.org/nawrotlab/EI_clustered_network
    cd EI_clustered_network
    git annex get *
    mv * ../../data
    cd ../../
fi

chmod -R ugo+rwX data/
rm -rf tmp



























