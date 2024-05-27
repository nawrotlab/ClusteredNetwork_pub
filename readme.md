# Spiking attractor model of motor cortex explains modulation of neural and behavioral variability by prior target information
This is a Python implementation of E/I clustered neural network together with codes to reproduce the figures presented in the paper.

**Vahid Rostami, Thomas Rost, Felix Schmitt, Sacha van Albada, Alexa Riehle, Martin Nawrot. "Spiking attractor model of motor cortex explains modulation of neural and behavioral variability by prior target information."**


## Table of Contents
- [Project Structure](#project-structure)
- [Reproducing Figures](#reproducing-figures)
- [Accessing Data](#accessing-data)
- [Environment Setup](#environment-setup)
- [Docker Image for Code Execution](#docker-image-for-code-execution)

## Project Structure
This project utilizes Python and Nest Simulator for analyzing experimental data, simulating spiking neural networks (SNN), and producing figures.

- **`fig_codes/`**: Contains Python scripts to plot all paper figures.
- **`data/`**: Includes all experimental and simulated data required to reproduce the figures. The data is hosted on G-Node GIN and can be downloaded using the instructions below.
- **`src/`**: Contains Python scripts for executing SNN simulations and analyzing simulated/experimental data.

## Reproducing figures
To recreate specific figures, execute the following command within the fig_codes directory:
```bash
python figX.py
```
Replace **'X'** with the figure number. This will generate **'figX.pdf'**, or **'figX.png'** within the **'fig_codes'** folder.

## Accessing Data
Experimental data and simulation results are also available on G-Node GIN in the repository following repositories:
- Experimental data [nawrotlab/delayed_center-out_uncertainty_Riehle](https://gin.g-node.org/nawrotlab/delayed_center-out_uncertainty_Riehle)
- preprocessed and simulated data [nawrotlab/EI_clustered_network](https://gin.g-node.org/nawrotlab/EI_clustered_network).
This repository is roughly 16GB in size. To download the data via the web interface, 
follow the instructions on the provided link. We recommend using the command line and 
[git-annex](https://git-annex.branchable.com/install/) for downloads:

```bash
mkdir data
git clone https://gin.g-node.org/nawrotlab/delayed_center-out_uncertainty_Riehle
mv -r delayed_center-out_uncertainty_Riehle/pickle data/experimental_data
git clone https://gin.g-node.org/nawrotlab/EI_clustered_network
cd EI_clustered_network
git annex get *
mv -r preprocessed_and_simulated_data ../data/
```

Alternatively, utilize the provided script to download the data. The script accepts an optional flag -e
to download only the experimental data.
```bash
./Download.sh # or ./Download.sh -e
```
This script creates a ***'data'*** folder in the repository and initiates the download. 
It verifies if the data is already present and skips download if it exists. 
Note that the download may take a considerable amount of time, and git-annex might appear stalled but will resume eventually.

## Environment Setup
The `environment.yml` file contains necessary packages to execute the code. To create a Conda environment:

```bash
conda env create -f environment.yml
conda activate ClusteredNetwork_pub
```
Note: Some dependencies might need to be installed outside the conda environment.

Alternatively, use the provided Docker image (recommended). See the "Docker Image for Code Execution" section below for details.

## Docker Image for Code Execution
We provide a docker image, 
[fschmitt/clustered_network_pub:nest2_20](https://hub.docker.com/repository/docker/fschmitt/clustered_network_pub/), 
to run the code.
The image is accessed via Docker Hub. To use:

```bash 
docker pull fschmitt/clustered_network_pub:nest2_20
docker run -d   -it   --name clusternet   --mount type=bind,source="$(pwd)"/ClusteredNetwork_pub,target=/app   fschmitt/clustered_network_pub:nest2_20
docker exec -it clusternet /bin/bash
```

Once inside the container, execute the download script or run the code as previously described. To exit the container:
```bash
exit
docker stop clusternet
docker rm clusternet
```

If you prefer not to mount the repository into the docker image, you can clone it inside the container:
```bash
git clone https://github.com/nawrotlab/ClusteredNetwork_pub.git
cd ClusteredNetwork_pub
```
### Known problems of Docker
Older docker version might not automatically set up a functioning network bridge. The download_data.sh script will thus not be able to access the internet and fail.
You can circumvent this by creating a bridge manually:
```bash
docker network create --driver bridge common
docker run -d -it --network common --name clusternet --mount type=bind,source="$(pwd)"/ClusteredNetwork_pub,target=/app fschmitt/clustered_network_pub:nest2_20
```

Please cite the paper if you use any part of this code.

If you encounter any problems, feel free to create a GitHub issue.
