"Run the tests of the listed packages that are loaded and write the result as JSON for pds.
 Wrapped in a block so this template can follow a load script (temporaries must come first)."
[ | suite result |
suite := TestSuite named: 'pds snapshot'.
{{TEST_PACKAGES}} do: [ :packageName |
	(PackageOrganizer default packageNamed: packageName ifAbsent: [ nil ]) ifNotNil: [ :package |
		(package definedClasses select: [ :each | (each inheritsFrom: TestCase) and: [ each isAbstract not ] ])
			do: [ :each | suite addTests: each buildSuite tests ] ] ].
result := suite run.
{{RESULTS_FILE}} asFileReference ensureDelete; writeStreamDo: [ :stream |
	stream nextPutAll: (STON toJsonString: (Dictionary new
		at: 'run' put: result runCount;
		at: 'passed' put: result passedCount;
		at: 'failures' put: (result failures collect: [ :each | each printString ]) asArray;
		at: 'errors' put: (result errors collect: [ :each | each printString ]) asArray;
		yourself)) ] ] value.
