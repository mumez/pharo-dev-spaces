"Entry point of prepare-dev-base: file in every libs/*.st in file name order
 (001_agentic_browser.st, then e.g. 002_xxx.st added by the user), then save and quit.
 Fail-fast: the first failing script stops the build, and the error names that script."
(({{LIBS_DIR}} asFileReference filesMatching: '*.st') sorted: [ :a :b | a basename < b basename ])
	do: [ :each |
		Transcript crShow: '## Loading ' , each basename , ' ##'.
		[ each fileIn ] on: Error do: [ :error |
			error messageText: each basename , ' failed: ' , error messageText.
			error pass ] ].

Smalltalk snapshot: true andQuit: true.
