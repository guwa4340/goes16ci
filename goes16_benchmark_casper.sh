#!/bin/bash -l
#SBATCH --job-name=goes16ci
#SBATCH --account=NAML0001
#SBATCH --ntasks=32
#SBATCH --cpus-per-task=1
#SBATCH --time=00:20:00
#SBATCH --partition=dav
#SBATCH --gres=gpu:v100:8
#SBATCH --exclusive
#SBATCH --mem=128G
module purge
module load gnu/7.3.0 openmpi-x python/3.6.8 cuda/10.0
source /glade/work/dgagne/ncar_pylib_dl_10/bin/activate
cd ~/goes16ci
python setup.py install
python -u goes16_deep_learning_benchmark.py >& goes_deep.log