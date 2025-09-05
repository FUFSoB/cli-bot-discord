from typing import Awaitable, Optional, Pattern
import regex
import bashlex
from models.errors import NoCommandError, ParsingError
from models.utils import run_in_executor
from .processing import Processor

__all__ = ("parse", "get_processor")


eof_code_block: Pattern = regex.compile(r"(<<\s*)```(\w*)(\s+.*?\n)```$", regex.DOTALL)

mention_regex: Pattern = regex.compile(
    r"""((?!'|")<(@!|@&|@|\#|a:|:)([\w_]+:\d{17,19}|\d{17,19})>(?!'|"))"""
)

# brackets: Pattern = regex.compile(r"(.*?(?=\())\(((?:[^()]|(?R))*?)\)")


# def brackets_replace(match):
#     string, first, second = match[:]
#     if (
#         first.endswith("$") or first.strip().count(" ") == 0
#         or (first.endswith("\\") and second.endswith("\\"))
#     ):
#         return string

#     else:
#         return string.replace("(", "\\(").replace(")", "\\)")


def parse(content: str) -> tuple[list, str]:
    """
    Parse content and return bash ast.
    """
    content = mention_regex.sub(lambda x: repr(x[0]), content.strip())

    final_content = (
        "\n".join(
            x.rstrip()  # remove trailing spaces as they break bashlex
            for x in content.split("\n")
            if (
                (y := x.strip())  # pass a line only if it has something but spaces
                and not y.startswith("#")  # skip comments as they break bashlex
            )
        )
        .replace("\n\\n", "\n\n")
        .replace("\\\n", " ")
    )

    if not final_content:
        raise NoCommandError()

    if "```" in final_content:
        final_content: str = eof_code_block.sub(
            r"\1BLOCK_EOF\3BLOCK_EOF", final_content
        )

    # if "(" in final_content:
    #     final_content = brackets.sub(brackets_replace, final_content)
    #     print(repr(final_content))

    prev = []
    while True:
        try:
            return bashlex.parse(final_content), final_content

        except bashlex.errors.ParsingError as ex:
            # all this block made to prevent noisy bash parsing error
            # on brackets that don't go up with function definition
            msg = str(ex)
            if msg in prev:
                raise ParsingError(msg)
            prev.append(msg)

            if "unexpected token" in ex.message:
                source = ex.s
                position = ex.position

                # print(
                #     repr(source),
                #     repr(source[:position + 1]),
                #     position,
                #     ex.message
                # )

                if "'('" in ex.message:
                    replaced = source[:position] + "\\(" + source[position + 1 :]
                    final_content = final_content.replace(source, replaced, 1)
                    continue

                elif "')'" in ex.message:
                    replaced = source[:position] + "\\)" + source[position + 1 :]
                    final_content = final_content.replace(source, replaced, 1)
                    continue

                # # the next two checks are made to fix comment and new lines
                # # implicitly after error (because they can be successfully
                # # used in heredocs and other places)
                # elif "#" in final_content:  # workaround for bad #
                #     final_content = (
                #         final_content[:position].rsplit("#", 1)[0]
                #         + final_content[position:].split("\n", 1)[-1]
                #     )
                #     continue

                # elif source.startswith("\n"):
                #     replaced = source.removeprefix("\n")
                #     final_content = final_content.replace(
                #         source, replaced, 1
                #     )
                #     continue

                # elif "\n\n" in final_content:  # workaround for bad \n\n
                #     final_content = (
                #         final_content[:position]
                #         + final_content[position:].replace("\n\n", "\n", 1)
                #     )
                #     continue

                elif "(" in final_content:
                    final_content = final_content[: position - 2] + final_content[
                        position - 2 :
                    ].replace("(", "\\(", 1)
                    continue

                else:
                    break

            raise ParsingError(msg)

        except NotImplementedError as ex:
            raise ParsingError(f"Unimplemented feature: {ex}")

        except Exception:
            raise ParsingError("Unknown error happened")


@run_in_executor
def get_processor(content: str, path: Optional[str] = None) -> Awaitable[Processor]:
    """
    Parse content and create processor object.
    """
    if path and content.startswith("#!"):
        content = content.split("\n", 1)[0].removeprefix("#!") + " " + path
    data, content = parse(content)
    return Processor(content, data)
