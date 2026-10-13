"Load packages straight from Tonel in projects.json order, as SIS import_package does: #( srcPath packageName ).
 No Metacello / Iceberg involved, so dependencies are not reloaded and no repository cache can go stale."
{{PACKAGE_SOURCES}} do: [ :each | | reader |
	reader := TonelReader on: (each at: 1) asFileReference fileName: (each at: 2).
	reader loadPackage.
	reader snapshot updatePackage: reader package ].
