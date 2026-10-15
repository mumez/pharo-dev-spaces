"Load each repository through its baseline, in projects.json order: #( baselineName repositoryUrl groups ).
 `get` reloads a BaselineOf already in the image (incremental builds), so changed specs are not ignored."
{{PROJECTS}} do: [ :each |
	Metacello new
		baseline: (each at: 1);
		repository: (each at: 2);
		onUpgrade: [ :upgrade | upgrade useIncoming ];
		onConflictUseIncoming;
		get;
		load: (each at: 3) ].
