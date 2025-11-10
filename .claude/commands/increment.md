Increment the project version number using `make increment_version`.

IMPORTANT: Never manually edit version numbers in package.json. Always use the Makefile target.

Steps:
1. Run `make increment_version` to bump the patch version
2. Show the old and new version numbers
3. Stage package.json and package-lock.json if they changed
4. Do NOT commit automatically - let the user decide when to commit
