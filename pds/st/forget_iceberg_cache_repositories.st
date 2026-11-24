"Forget the Iceberg repositories cloned into pharo-local/iceberg. pds deletes that cache after loading
 (remove_iceberg_cache), so their registrations would point at missing directories, and loading the same
 packages again (e.g. a dev-base dependency registered as a project) fails with NotFound in Iceberg.
 Repositories cloned elsewhere are kept.
 Keep in sync with remove_iceberg_cache in pds/image_dir.py, which deletes image_dir/pharo-local/iceberg:
 FileLocator localDirectory is the image's pharo-local directory, so both name the same cache."
(IceRepository registry select: [ :each |
	each location notNil and: [ (FileLocator localDirectory / 'iceberg') resolve contains: each location resolve ] ])
		do: [ :each | each forget ].
