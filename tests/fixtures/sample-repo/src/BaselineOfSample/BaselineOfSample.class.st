Class {
	#name : 'BaselineOfSample',
	#superclass : 'BaselineOf',
	#category : 'BaselineOfSample',
	#package : 'BaselineOfSample'
}

{ #category : 'baseline' }
BaselineOfSample >> baseline: spec [

	<baseline>
	spec for: #pharo do: [
		self rediStick: spec.
		spec package: 'Sample-Model' with: [spec requires: #('Sample-Core' 'RediStick')].
		spec package: 'Sample-Core' with: [spec requires: #('RediStick')].
		spec package: 'Sample-Tests' with: [spec requires: #('Core')].
		spec
			group: 'default' with: #( 'Core' 'Tests' );
			group: 'Core'
			with:
				#( 'Sample-Model' 'Sample-Core' );
			group: 'Tests' with: #( 'Sample-Tests' ).
		self optionExtra: spec.
		]
]

{ #category : 'baseline' }
BaselineOfSample >> optionExtra: spec [

	spec package: 'Sample-Extra' with: [ spec requires: 'Sample-Core' ].
	spec group: 'Extra' with: 'Sample-Extra'
]

{ #category : 'external projects' }
BaselineOfSample >> rediStick: spec [
	spec
		baseline: 'RediStick'
		with: [ spec
				repository: 'github://mumez/RediStick/repository';
				loads: 'StreamObjects' ]
]
