import click
from   ..gh         import ACCEPT
from   ..inspecting import inspect_project
from   ..util       import readcmd, runcmd

TOPICS_ACCEPT = f'application/vnd.github.mercy-preview,{ACCEPT}'

@click.command()
@click.option('--repo-name', metavar='NAME')
@click.pass_obj
def cli(obj, repo_name):
    env = inspect_project()
    if repo_name is None:
        repo_name = env["repo_name"]
    repo = obj.gh.user.repos.post(json={
        "name": repo_name,
        "description": env["short_description"],
    })
    obj.gh[repo["url"]].topics.put(
        headers={"Accept": TOPICS_ACCEPT},
        json={"names": env["keywords"] + ["python"]},
    )
    if 'origin' in readcmd('git', 'remote').splitlines():
        runcmd('git', 'remote', 'rm', 'origin')
    runcmd('git', 'remote', 'add', 'origin', repo["ssh_url"])
    runcmd('git', 'push', '-u', 'origin', 'master')
