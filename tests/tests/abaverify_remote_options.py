
# Remote run directory [Default is abaverify_temp]
# Command line run directory will override the value specified here if both are provided
#remote_run_directory = 'abaverify_temp'


# Add files to copy to the remote [Default is empty list]
# Paths relative to /tests directory
#local_files_to_copy_to_remote = ['CompDam.parameters', 'sample.props']


# Regular expression for source files to copy [Default is below]
#source_file_regexp = r'.*\.for$'


# Copy results back to local directory? [Defualt is False]
copy_results_to_local = True


# Name of environment file to use on remote [Default is 'abaqus_v6_remote.env']
# The file is automatically renamed abaqus_v6.env on the remote
environment_file_name = 'abaqus_v6_remote.env'