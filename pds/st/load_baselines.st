"Load each repository through its baseline, in st-projects.json order: #( baselineName repositoryUrl groups ).
 `get` reloads a BaselineOf already in the image (incremental builds), so changed specs are not ignored.
 A local project already loaded is kept when another project references it as a dependency
 (e.g. github://... in a BaselineOf), so the local sources are not replaced by the remote ones."
| projects localBaselineNames |
projects := {{PROJECTS}}.
localBaselineNames := projects collect: [ :each | each at: 1 ].
projects do: [ :each |
	| preferLoadedLocalDependency |
	preferLoadedLocalDependency := [ :resolution :loaded :incoming |
		((localBaselineNames includes: loaded projectName) and: [ loaded projectName ~= (each at: 1) ])
			ifTrue: [ resolution useLoaded ]
			ifFalse: [ resolution useIncoming ] ].
	Metacello new
		baseline: (each at: 1);
		repository: (each at: 2);
		onUpgrade: preferLoadedLocalDependency;
		onDowngrade: preferLoadedLocalDependency;
		onConflict: preferLoadedLocalDependency;
		get;
		load: (each at: 3) ].
