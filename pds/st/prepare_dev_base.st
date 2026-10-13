Metacello new
	baseline: 'PharoSmalltalkInteropServer';
	repository: 'github://mumez/PharoSmalltalkInteropServer:main/src';
	onConflictUseIncoming;
	load.

Metacello new
	baseline: 'AgenticBrowser';
	repository: 'github://mumez/pharo-agentic-browser:main/src';
	onConflictUseIncoming;
	load: #('all').
