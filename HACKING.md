# How to release from `main`
 
- `git checkout main`
- `git pull`
- `git tag <version-id>`, for example `git tag 0.0.14`
- `git push origin tag <version-id>`, for example `git push origin tag 0.0.14`

Go to https://github.com/canonical/cos-lib/releases and click on 'Draft a new release'.

Select the tag you've just created from the dropdown and the `main` branch as target.
Enter a meaningful release title and in the description, put an itemized changelog listing new features and bugfixes, and whatever is good to mention.

Click on 'Publish release'.

Profit!