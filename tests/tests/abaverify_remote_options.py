
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


# Specify file extensions to indicate which files should be copied back to local working directory
# It is assumed that the filename = job name
# This option is only relevant when copy_results_to_local = True
# Default is ['.dat', '.inp', '.msg', '.odb', '.sta']
#file_extensions_to_copy_to_local = ['.dat', '.inp', '.msg', '.odb', '.sta']


# Specify which files to copy back from remote to local after job ends (full file name; i.e. for files where filename != job name)
# This is useful for files where the file name != job name
# This option is only relevant when copy_results_to_local = True
#files_to_copy_to_local = ['debug.py']


# Name of environment file to use on remote [Default is 'abaqus_v6_remote.env']
# The file is automatically renamed abaqus_v6.env on the remote
environment_file_name = 'abaqus_v6_remote.env'