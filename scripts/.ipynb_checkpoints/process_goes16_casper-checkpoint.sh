#!/bin/bash -l
#SBATCH --job-name=goes16_process
#SBATCH --account=NAML0001
#SBATCH --time=4:00:00
#SBATCH --partition=dav
#SBATCH --ntasks=36
#SBATCH --ntasks-per-node=36
#SBATCH -e goes16_process.log
#SBATCH -o goes16_process.log
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=dgagne
export PATH="/glade/u/home/dgagne/miniconda3/envs/tf2/bin:$PATH"
cd $HOME/goes16ci/scripts
python -u process_goes16.py goes16_process_config_32.yml -n 36 -a 
python -u process_goes16.py goes16_process_config_64.yml -n 36 -a
python -u process_goes16.py goes16_process_config_128.yml -n 36 -a