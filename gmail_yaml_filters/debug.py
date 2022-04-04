import functools
import sys

from rich import print


def log_filter(action, data):
    icon_map = {
        'create': '✨',
        'delete': '❌',
    }
    icon = icon_map[action]

    print(
        icon,
        '[underline]if[/]',
        '\n      '.join(
            f'{key} {repr(value)}'
            for (key, value)
            in data['criteria'].items()
        ),
        file=sys.stderr,
    )
    print(
        '  ',
        '[underline]then[/]',
        '\n        '.join(
            f'{key} {value}'
            for (key, value)
            in data['action'].items()
        ),
        file=sys.stderr,
    )


log_new_filter = functools.partial(log_filter, 'create')
log_delete_filter = functools.partial(log_filter, 'delete')


def log_new_label(name):
    print(f'🔖 Creating label [bold]{name}[/]', file=sys.stderr)


def log_delete_label(data):
    print(
        f"❌ Deleting label [bold]{data['name']}[/]",
        f"(id={data['id']})",
        file=sys.stderr,
    )
