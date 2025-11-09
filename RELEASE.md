# Release Guide

Create release tags using semantic versioning. Version is managed via hatch and synced between `package.json` and Python package metadata.

## Version Management

Update version using hatch (automatically creates git tag):

```bash
hatch version <new-version>
```

Version follows semantic versioning via [hatch-nodejs-version](https://github.com/agoose77/hatch-nodejs-version#semver).

## Build

Clean development artifacts before building:

```bash
jlpm clean:all
git clean -dfX  # Optional: clean all untracked files
```

Build distribution packages:

```bash
python -m build
```

This creates `.tar.gz` and `.whl` files in `dist/`. Note: `python setup.py sdist bdist_wheel` is deprecated and unsupported.
