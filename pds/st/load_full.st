"Load each repository through its baseline, in projects.json order: #( baselineName repositoryUrl groups )."
{{PROJECTS}} do: [ :each |
	Metacello new
		baseline: (each at: 1);
		repository: (each at: 2);
		onUpgrade: [ :upgrade | upgrade allow ];
		onConflictUseIncoming;
		load: (each at: 3) ].
