# Release Guide

JupyterLab Notifications Extension releases to PyPI and npm using manual or automated workflows via Jupyter Releaser.

## Manual Release

Manual releases provide direct control over the publication process. This approach builds and publishes packages directly to PyPI and npm registries.

**Prerequisites:**
- Build tools: `pip install build twine hatch`
- npm credentials configured
- PyPI credentials configured

**Version Management:**

Update version using hatch (automatically creates git tag):

```bash
hatch version <new-version>
```

Version follows semantic versioning via [hatch-nodejs-version](https://github.com/agoose77/hatch-nodejs-version#semver). The version is synced between `package.json` and Python package metadata.

**Build Process:**

Clean development artifacts before building:

```bash
jlpm clean:all
git clean -dfX  # Optional: clean all untracked files
```

Build Python distribution packages (wheel and source):

```bash
python -m build
```

This creates `.tar.gz` and `.whl` files in `dist/`. Note: `python setup.py sdist bdist_wheel` is deprecated and unsupported.

**Publishing:**

Upload to PyPI:

```bash
twine upload dist/*
```

Publish npm package:

```bash
npm login
npm publish --access public
```

## Automated Release (Jupyter Releaser)

Jupyter Releaser automates version bumping, changelog generation, and publishing through GitHub Actions workflows.

**Setup Requirements:**
- GitHub repository configured per [Jupyter Releaser checklist](https://jupyter-releaser.readthedocs.io/en/latest/how_to_guides/convert_repo_from_repo.html)
- PyPI and npm tokens stored as GitHub secrets
- Workflow permissions enabled

**Release Steps:**

1. Navigate to repository Actions panel
2. Run "Step 1: Prep Release" workflow - generates draft changelog and bumps version
3. Review and edit draft changelog as needed
4. Run "Step 2: Publish Release" workflow - publishes to PyPI and npm

See [workflow documentation](https://jupyter-releaser.readthedocs.io/en/latest/get_started/making_release_from_repo.html) for detailed instructions.

## Conda Forge

For first-time conda-forge publication, follow [adding packages guide](https://conda-forge.org/docs/maintainer/adding_pkgs.html).

Once published, conda-forge bot automatically detects new PyPI releases and opens pull requests on the feedstock repository.
