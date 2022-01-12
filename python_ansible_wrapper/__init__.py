import logging
from os.path import basename
from pathlib import Path
from subprocess import run
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterator, List, Union

import yaml
from chromalog.mark.helpers.simple import important

log = logging.getLogger(__name__)


class Block:
    def __init__(self, name: str, *, root: Path):
        self._name: str = name
        self._tasks: List[Union[Block, Dict[str, Any]]] = []
        self._root = root

    def apt_present(self, packages: List[str], *, title: str = None) -> None:
        if title is None:
            title = f"Install {', '.join(packages)}"

        # FIXME: do we want to run apt-update first?
        self._tasks.append({
            "name": title,
            "become": True,
            "apt": {
                "name": packages,
                # FIXME: do we want this turned on?
                # "update_cache": True,
            },
        })

    def mkdir(self, path: str, *, owner: str = 'root', mode: str) -> None:
        self._tasks.append({
            "name": f"mkdir {path}",
            "become": True,
            "file": {
                "path": path,
                "state": "directory",
                "owner": owner,
                "group": owner,
                "mode": mode,
            },
        })

    def other(
        self,
        name: str,
        *,
        become: str,
        **detail: Any,
    ) -> None:
        self._tasks.append({
            # see https://docs.ansible.com/ansible/latest/modules/ufw_module.html
            "name": name,
            "become": True,
            "become_user": become,
            **detail,
        })

    def gitclone(
        self,
        *,
        url: str,
        dest: str,
        owner: str,
        ref: str,
        update: bool,
    ) -> None:
        task = {
            "name": f"Clone {url} to {dest}",
            "become": True,
            "git": {
                "dest": dest,
                "repo": url,
                "version": ref,
                "update": update,
            }
        }

        task['become_user'] = owner

        self._tasks.append(task)

    def command(
        self,
        title: str,
        command: List[str],
        chdir: str = None,
        become: str = None,
    ) -> None:
        # See https://docs.ansible.com/ansible/latest/modules/command_module.html#command-module
        detail: Dict[str, Any] = {
            "argv": command,
        }
        if chdir is not None:
            detail['chdir'] = chdir
        task = {
            "name": title,
            "become": True,
            "command": detail,
        }
        if become is not None:
            task['become_user'] = become

        self._tasks.append(task)

    def copy(
        self,
        *,
        title: str = None,
        src: Union[str, Path] = None,
        content: str = None,
        dest: str,
        root: bool = False,
        owner: str = None,
        mode: int = None
    ) -> None:
        # https://docs.ansible.com/ansible/latest/modules/copy_module.html
        how = {
            "dest": dest,
            "backup": True,
        }

        if title is None:
            assert src is not None
            title = f"Upload {basename(src)} to {dest}"

        if src is not None:
            assert content is None
            if isinstance(src, Path):
                how['src'] = str(src)
            else:
                how['src'] = str(self._root / src)
        else:
            assert content is not None
            how['content'] = content

        if mode is not None:
            how['mode'] = mode

        task: Dict[str, Any] = {
            "name": title,
            "copy": how,
        }

        if root:
            assert owner is None or owner == 'root'
            task["become"] = True
        elif owner is not None:
            task["become"] = True
            task["become_user"] = owner

        self._tasks.append(task)

    def get_tasks(self) -> Iterator[Dict[str, Any]]:
        for task in self._tasks:
            if isinstance(task, dict):
                yield task
            else:
                assert isinstance(task, Block)
                yield {
                    "name": task._name,
                    "block": list(task.get_tasks()),
                }

    def get_block(self, name: str) -> "Block":
        block = Block(name, root=self._root)
        self._tasks.append(block)
        return block


class Play(Block):
    def __init__(self, name: str, *, root: Path):
        assert '/' not in name
        assert name.endswith('.yml')

        super().__init__(name, root=root)

    def run_play(self, *, hosts: str, saveas: Path = None, verbosity: int = 0) -> None:
        if saveas is None:
            with TemporaryDirectory() as tmpdir:
                self._run_play(saveas=Path(tmpdir) / self._name, hosts=hosts, verbosity=verbosity)
        else:
            self._run_play(saveas=saveas, hosts=hosts, verbosity=verbosity)

    def _run_play(self, *, hosts: str, saveas: Path, verbosity: int) -> None:
        assert len(self._tasks), "No tasks"

        log.info(f"Generating playbook {important(saveas.relative_to(self._root))}")
        with open(saveas, 'w') as f:
            yaml.dump([{"hosts": hosts, "tasks": list(self.get_tasks())}], f)

        # note: our environment should already contain $ANSIBLE_CONFIG and
        # $ANSIBLE_INVENTORY
        cmd = [
            'ansible-playbook',
            str(saveas),
        ]
        cmd.extend(['--verbose'] * verbosity)
        log.info(f"Running ansible-playbook {important(saveas.relative_to(self._root))}")
        run(cmd, cwd=self._root, check=True)
