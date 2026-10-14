[Metacello new
  baseline: 'AgenticBrowser';
  repository: 'github://mumez/pharo-agentic-browser:main/src';
  onConflict: [ :e | e useIncoming ];
  onUpgrade: [ :e | e useIncoming ];
  ignoreImage;
  load: 'all'] on: MCMergeOrLoadWarning do: [ :ex | ex load ].

Transcript crShow: '## AgenticBrowser loaded ##'.

Smalltalk snapshot: true andQuit: true.
