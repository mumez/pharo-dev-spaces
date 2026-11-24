"Load each repository through its baseline, in st-projects.json order: #( baselineName repositoryUrl groups ).
 `get` reloads a BaselineOf already in the image (incremental builds), so changed specs are not ignored.
 A local project already loaded is kept when another project references it as a dependency
 (e.g. github://... in a BaselineOf), so the local sources are not replaced by the remote ones.
 Iceberg repositories in the (deleted) pharo-local/iceberg cache are forgotten before loading, so stale
 registrations from the base image do not break the load, and after loading, before the image is saved.
 A package modified in the image is overwritten by the loaded version: the MCMergeOrLoadWarning dialog
 would otherwise block the headless image forever. This applies to every package being loaded, including a
 deliberate in-image change to a listed project, which is intended: a build loads the sources from git.
 It does not touch a local project kept with useLoaded above, because its packages are not loaded again."
| projects localBaselineNames |
projects := {{PROJECTS}}.
localBaselineNames := projects collect: [ :each | each at: 1 ].
{{FORGET_ICEBERG_CACHE_REPOSITORIES_SCRIPT}} asFileReference fileIn.
projects do: [ :each |
	| preferLoadedLocalDependency |
	preferLoadedLocalDependency := [ :resolution :loaded :incoming |
		((localBaselineNames includes: loaded projectName) and: [ loaded projectName ~= (each at: 1) ])
			ifTrue: [ resolution useLoaded ]
			ifFalse: [ resolution useIncoming ] ].
	[ Metacello new
		baseline: (each at: 1);
		repository: (each at: 2);
		onUpgrade: preferLoadedLocalDependency;
		onDowngrade: preferLoadedLocalDependency;
		onConflict: preferLoadedLocalDependency;
		get;
		load: (each at: 3) ] on: MCMergeOrLoadWarning do: [ :warning | warning load ] ].
{{FORGET_ICEBERG_CACHE_REPOSITORIES_SCRIPT}} asFileReference fileIn.
