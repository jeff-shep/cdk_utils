from typing import List
from invoke import task

@task
def build(context, _docs=False, _bytecode=False, _extra=""):
    context.run("python -m build")


@task
def publish(context, _docs=False, _bytecode=False, _extra=""):
    context.run("python -m twine upload --repository metoffice dist/* --verbose")

@task
def formatting(context, docs=False, bytecode=False, extra=""):
    context.run("python -m black .")


@task
def linting(context, _docs=False, _bytecode=False, _extra=""):
    folders = [".\\src", ".\\test"]
    context.run(f"pylint --fail-under 10 {_join_with_spaces(folders)}")


@task
def tests(context, _docs=False, _bytecode=False, _extra=""):
    context.run("python -m pytest")

def _join_with_spaces(strings: List[str]) -> str:
    return " ".join(strings)
