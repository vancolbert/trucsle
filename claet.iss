#define v 20241019
[Setup]
AppName=Landes Eternelles 1.9.5 claet/test
AppVersion={#v}
WizardStyle=modern
DefaultDirName={autopf}\Landes Eternelles
DefaultGroupName=Landes Eternelles
Compression=lzma2
SolidCompression=yes
OutputDir=.
OutputBaseFilename=setup-LE195_claet_test_{#v}
AlwaysShowDirOnReadyPage=yes
MissingMessagesWarning=yes
NotRecognizedMessagesWarning=yes
UsePreviousAppDir=no
AppPublisher=L'Association d'Hommes Bleus qui Portent des Bottes Oranges pour se Sentir en Sécurité
AppPublisherURL=https://github.com/vancolbert/claet
SetupIconFile=claet.ico
[Files]
Source: "LE195_claet_test_{#v}.exe"; DestDir: "{app}"
Source: "claet.ico"; DestDir: "{app}"
[Icons]
Name: "{group}\LE195 claet test {#v}"; Filename: "{app}\LE195_claet_test_{#v}.exe"; WorkingDir: "{app}"; IconFilename: "{app}\claet.ico"
Name: "{autodesktop}\LE195 claet test {#v}"; Filename: "{app}\LE195_claet_test_{#v}.exe"; WorkingDir: "{app}"; IconFilename: "{app}\claet.ico"
Name: "{group}\{cm:UninstallProgram}"; Filename: "{uninstallexe}"; IconFilename: "{app}\claet.ico"
[Languages]
Name: en; MessagesFile: "compiler:Default.isl"
Name: fr; MessagesFile: "compiler:Languages\French.isl"
[Messages]
en.BeveledLabel=English
fr.BeveledLabel=French
