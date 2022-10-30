# Changelog

<!--next-version-placeholder-->

## v0.3.0 (2022-10-30)
### Feature
* Remove "under development" warnings, the code is stable enough ([`6e5518b`](https://github.com/vdmit11/contextvars-extras/commit/6e5518bd4be621f4f481297225970a05bb5abd7f))

## v0.2.1 (2022-06-21)
### Fix
* ContextVarsRegistry.keys() triggers deferred_default ([`fc17c59`](https://github.com/vdmit11/contextvars-extras/commit/fc17c59c3518efa4190cef5a1ce7f02088df210a))

## v0.2.0 (2022-06-21)
### Feature
* New method: `ContextVarExt.is_gettable` ([`77ff938`](https://github.com/vdmit11/contextvars-extras/commit/77ff9382bb72026905d86f0872e95316ee85a255))
* New flag: `ContextVarExt.default_is_set` ([`296fc9f`](https://github.com/vdmit11/contextvars-extras/commit/296fc9fefc00ce56020fd56556e98f4317987fb1))

## v0.1.0 (2022-02-14)
### Feature
* Allow setting properties using `with registry(var=value)` ([`0a02cf6`](https://github.com/vdmit11/contextvars-extras/commit/0a02cf6d0f263f743def3c8c66bf9e20302930c2))

## v0.0.12 (2022-02-12)
### Fix
* Missing type stub for ContextVarExt.deferred_default attribute ([`b088ea9`](https://github.com/vdmit11/contextvars-extras/commit/b088ea94fd9eaafdf802c8011e6224459d9b1958))

## v0.0.11 (2022-02-12)
### Fix
* Wrong exception type thrown by ContextVarsRegistry.__delitem__ ([`876d342`](https://github.com/vdmit11/contextvars-extras/commit/876d3421519b2a8fca71eb1c0f9c596a3e816b49))

### Documentation
* Change order of classes to put ContextVarExt to the top ([`a115a64`](https://github.com/vdmit11/contextvars-extras/commit/a115a64e67ccd554b7fdf2a204f3a740b83b5981))

## v0.0.10 (2021-10-18)
### Fix
* Inconsistent defaults with existing ContextVar object ([`510e4e7`](https://github.com/vdmit11/contextvars-extras/commit/510e4e7674e1ce4cbcb0ff6408ce99348fa07318))
* Reset_to_default() doesn't when re-using existing ContextVar ([`2e57b3e`](https://github.com/vdmit11/contextvars-extras/commit/2e57b3e66a212631a79a88aa1484aaca40ab7843))

### Documentation
* Delete useless CHANGELOG.md full of debugging leftovers ([`535565e`](https://github.com/vdmit11/contextvars-extras/commit/535565e5789204fbb85f609e74105a8152660fdd))
