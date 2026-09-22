# iOS release versions

The public version is `expo.version` in `apps/ios/app.json`.
Starting with the backpack mascot release, use `0.1.1` and increment the patch
number for each subsequent intentional update: `0.1.2`, `0.1.3`, and so on.
After `0.1.9`, use `0.1.10`. Each component is an integer, not a decimal digit.

The internal `ios.buildNumber` remains separate. EAS production auto-increments
it for each new build. Version `0.1.1` is build `12`.

Retry a failed App Store upload using the existing build ID. Do not rebuild or
change either version solely because Apple returned a transient server error.
Changing the public version of an already-created IPA requires a new build.

EAS build quotas are independent of version numbers. Check the account's
current plan and usage before reporting remaining builds. Do not infer usage
from `buildNumber`, and do not change billing plans without user authorization.
