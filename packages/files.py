from models.packages import Package, file_commands


class files(Package):
    """
    Package that contains file-commands (stored in /scripts).
    """

    skip_files = True
    version = "0.0"
    commands = file_commands
