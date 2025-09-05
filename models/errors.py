from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import argparse
    from models.packages import Command
    from structure.filesystem import BaseFile


class ErrorKind:
    BEFORE = "before"
    IN = "in"
    DURING = "during"
    WHILE = "while"
    AFTER = "after"


class BaseError(Exception):
    """
    Base error class.
    """

    def __init__(self, text):
        super().__init__(text)

    def __bool__(self):
        return False


class BotError(BaseError):
    """
    Standard class to return description of error.
    """

    def __init__(
        self,
        text: str,
        point: Optional[str | bool] = None,
        kind: ErrorKind = ErrorKind.IN,
    ):
        if point:
            point = f"Error occured {kind} {point}:\n"
        elif point is False:
            point = ""
        else:
            point = "Error occured:\n"
        text = "\n".join("  " + i for i in text.strip().split("\n"))

        super().__init__((point + text).lstrip())


class IgnoreError(BotError):
    """
    Class for errors we can ignore.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class FatalError(BotError):
    """
    Class for errors we connot ignore at all.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class FileSystemError(FatalError):
    """
    Class for filesystem errors.
    """

    def __init__(self, description: str):
        super().__init__(description, "working with filesystem", ErrorKind.WHILE)


class NoCommandError(IgnoreError):
    """
    Error for superssing empty strings in parser.
    """

    def __init__(self):
        super().__init__("No command passed", "parsing", ErrorKind.WHILE)


class ParsingError(FatalError):
    """
    Error for bashlex.errors.ParsingError
    """

    def __init__(self, message: str):
        super().__init__(message, "parsing", ErrorKind.WHILE)


class ArgparseError(FatalError):
    """
    Error for argparse.ArgumentError
    """

    def __init__(self, command: Command, ex: argparse.ArgumentError):
        super().__init__(
            f"Invalid value for argument {ex.argument_name}",
            f"{command.name!r} was executed",
            ErrorKind.BEFORE,
        )


class BoolError(IgnoreError):
    """
    Subclass for boolean-command errors.
    """

    def __init__(self, name: str):
        super().__init__(name, False)


class FalseError(BoolError):
    """
    Error for command false.
    """

    def __init__(self):
        super().__init__("False")


class NullError(BoolError):
    """
    Error for command null.
    """

    def __init__(self):
        super().__init__("Null")


class UnknownCommandError(FatalError):
    """
    Error for cases when user entered unknown command.
    """

    def __init__(self, command: str):
        super().__init__(f"Command not found: {command}", "execution", ErrorKind.DURING)


class UnavailableCommandError(FatalError):
    """
    Error for cases when user entered known command, but it is unavailable.
    """

    def __init__(self, command: str):
        super().__init__(
            f"Command unavailable: {command}", "execution", ErrorKind.DURING
        )


class CommandPermissionError(FatalError):
    """
    Error for cases when user didn't match to command permission level.
    """

    def __init__(self, command: Command, group: Optional[str] = None):
        super().__init__(
            f"Missing {group or command.group!r} group "
            "that is required to execute command.",
            f"{command.name!r} was executed",
            ErrorKind.BEFORE,
        )


class MissingRequiredArgumentError(FatalError):
    """
    Error for cases when user didn't enter required positional argument.
    """

    def __init__(self, command: str, arg: str):
        super().__init__(
            f"Positional argument missing: {arg}",
            f"executing command {command!r}",
            ErrorKind.BEFORE,
        )


class MissingRequiredOptionError(FatalError):
    """
    Error for cases when user didn't enter any required flag.
    """

    def __init__(self, command: str, opt: str):
        super().__init__(
            f"Required flag missing: {opt}",
            f"executing command {command!r}",
            ErrorKind.BEFORE,
        )


class MissingRequiredStdinError(FatalError):
    """
    Error for cases when user didn't provide stdin to command.
    """

    def __init__(self, command: str):
        super().__init__(
            "Stdin missing", f"executing command {command!r}", ErrorKind.BEFORE
        )


class UndefinedVariableError(FatalError):
    """
    Error for cases when user tries to get or edit unknown variable.
    """

    def __init__(self, name: str):
        super().__init__(f"Unknown variable: {name}", "execution", ErrorKind.DURING)


class ReservedVariableError(FatalError):
    """
    Error for cases when user tries to set reserved variable.
    """

    def __init__(self, name: str):
        super().__init__(f"Reserved variable: {name}", "execution", ErrorKind.DURING)


class NoFileFoundError(FileSystemError):
    """
    Error for cases when file in filesystem cannot be found.
    """

    def __init__(self, name: str):
        super().__init__(f"No such file or directory: {name}")


class FileExistsError(FileSystemError):
    """
    Error for cases when file exists and user tries to create it.
    """

    def __init__(self, name: str):
        super().__init__(f"File already exists: {name}")


class PermissionDeniedError(FileSystemError):
    """
    Error for cases when file is unavailable for specific user.
    """

    def __init__(self, file: BaseFile, permission: str):
        super().__init__(f"Permission {permission!r} denied: {file} [{file.mode.info}]")


class NonEmptyDirectoryError(FileSystemError):
    """
    Error for cases when directory is not empty.
    """

    def __init__(self, file: BaseFile):
        super().__init__(f"Directory is not empty: {file}")


class NotADirectoryError(FileSystemError):
    """
    Error for cases when file is not a directory.
    """

    def __init__(self, file: BaseFile):
        super().__init__(f"Not a directory: {file}")


class NotAFileError(FileSystemError):
    """
    Error for cases when file is not a regular file.
    """

    def __init__(self, file: BaseFile):
        super().__init__(f"Not a regular file: {file}")


class NotAnExecutableError(FileSystemError):
    """
    Error for cases when file is not a regular file.
    """

    def __init__(self, file: BaseFile):
        super().__init__(f"Not an executable file: {file}")


class FileSizeError(FileSystemError):
    """
    Error for cases when user uploaded too powerful file.
    """

    def __init__(self, size: str, limit: str):
        super().__init__(f"Max file size exceeded: {size} (out of {limit})")


class DiscordError(FatalError):
    """
    Class for discord specific errors.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class NotAMentionError(DiscordError):
    """
    Error for cases when user provided invalid mention or ID.
    """

    def __init__(self, string: str):
        super().__init__(f"Not a mention: {string}", "parsing input", ErrorKind.WHILE)


class NotAMessageUrlError(DiscordError):
    """
    Error for cases when user provided invalid mention or ID.
    """

    def __init__(self, string: str):
        super().__init__(
            f"Not a message url: {string}", "parsing input", ErrorKind.WHILE
        )


class ObjectNotFoundError(DiscordError):
    """
    Error for cases when user provided invalid object that
    doesn't exist in his scope.
    """

    def __init__(self, id: int):
        super().__init__(f"Object not found: {id}", "object lookup", ErrorKind.DURING)


class ObjectUnspecifiedError(DiscordError):
    """
    Error for cases when user didn't provide object and it
    cannot be obtained from event.
    """

    def __init__(self, kind: str):
        super().__init__(
            f"Object is not specified: {kind}", "object lookup", ErrorKind.DURING
        )


class ObjectUnavailableError(DiscordError):
    """
    Error for cases when object is not available for current event.
    """

    def __init__(self, command: Command, name: str):
        super().__init__(
            f"Object is not available: {name}",
            f"{command.name!r} was executed",
            ErrorKind.BEFORE,
        )


class ShellError(FatalError):
    """
    Error for cases when there is a shell error.
    """

    def __init__(self, message: str):
        super().__init__(message, "shell execution", ErrorKind.DURING)


class LimitExceededError(FatalError):
    """
    Error for cases when user exceeded some kind of limitation.
    """

    def __init__(self, limit: str, description: str = ""):
        if description:
            description = "(" + description + ")"
        super().__init__(
            f"Limitation exceeded: {limit} {description}",
            "command execution",
            ErrorKind.DURING,
        )


class CommandError(FatalError):
    """
    Error for special command exceptions.
    """

    def __init__(self, command: Command | str, description: str):
        command_name: str = command if type(command) is str else command.name
        super().__init__(description, f"{command_name!r} execution", ErrorKind.DURING)


class ConversionError(CommandError):
    """
    Error for type Conversion errors.
    """

    def __init__(self, command: Command | str, type: str):
        super().__init__(command, f"Cannot convert value into {type}")


class InternalError(FatalError):
    """
    Error for internal errors.
    """

    def __init__(self, ex: Exception):
        __import__("traceback").print_exc()
        super().__init__(
            ex.__class__.__name__ + ": " + str(ex), "execution", ErrorKind.DURING
        )


class KeywordError(IgnoreError):
    """
    Subclass for special keywords errors.
    """

    def __init__(self, name: str):
        super().__init__(name, False)


class LoopError(KeywordError):
    """
    Subclass for loop-manipulating errors.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class BreakError(LoopError):
    """
    Error for break command.
    """

    def __init__(self):
        super().__init__("break")


class ContinueError(LoopError):
    """
    Error for continue command.
    """

    def __init__(self):
        super().__init__("continue")


class ReturnError(KeywordError):
    """
    Error for return command.
    """

    def __init__(self, value: Any):
        self.value = value
        super().__init__(f"return {type(value).__name__}")


# class IfPreEndError(KeywordError):
#     """
#     Error for stopping outer if-statements.
#     """
#     def __init__(self):
#         super().__init__("if-stop")


# class IfEndError(IfPreEndError):
#     """
#     Error for stopping if-statements.
#     """
#     def __init__(self):
#         super().__init__()


class NoPrefixError(IgnoreError):
    """
    Error for non-prefixed messages..
    """

    def __init__(self):
        super().__init__("No prefix found", "parsing", ErrorKind.BEFORE)


class ProcessError(FatalError):
    """
    Subclass for errors with processes.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class NoProcessFoundError(ProcessError):
    """
    Error for cases when process with requested PID is not found.
    """

    def __init__(self, pid: int):
        super().__init__(
            f"Process not found: {pid}", "working with processes", ErrorKind.WHILE
        )
