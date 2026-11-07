"""Recorder for the /api/test self-check run.

Each cloud contributes its own checks through clouds/<cloud>/selftest.py; this
holds the part that is the same for all of them - running a check, catching what
it raises, and accumulating the result rows the route returns.

Checks are passed as zero-argument callables rather than plain booleans so the
condition is evaluated inside the try. A payload with, say, compute_count="abc"
should fail one check, not raise out of the route.
"""


class Recorder:
    """Accumulates {group, name, status, error} rows for the response."""

    def __init__(self):
        self.results = []
        self.group = None

    def start(self, group):
        """Begin a group; subsequent checks are recorded against it."""
        self.group = group

    def run(self, name, fn):
        """Run `fn`; anything it raises marks the check failed."""
        try:
            fn()
            self.results.append({'group': self.group, 'name': name, 'status': 'pass'})
        except Exception as exc:
            self.results.append({'group': self.group, 'name': name,
                                 'status': 'fail', 'error': str(exc)})

    def check(self, name, predicate, message):
        """Record `name` as passed when `predicate()` is truthy.

        Replaces the `(_ for _ in ()).throw(AssertionError(...))` idiom the route
        used to need in order to raise from inside a lambda. `message` may be a
        string or a callable, so an expensive or failure-only message is not
        built for passing checks.
        """
        def _assert():
            if not predicate():
                raise AssertionError(message() if callable(message) else message)
        self.run(name, _assert)

    def fail(self, name, error):
        """Record a failure directly, for a step that blew up before checking."""
        self.results.append({'group': self.group, 'name': name,
                             'status': 'fail', 'error': str(error)})

    @property
    def passed(self):
        return sum(1 for r in self.results if r['status'] == 'pass')

    @property
    def failed(self):
        return sum(1 for r in self.results if r['status'] == 'fail')
