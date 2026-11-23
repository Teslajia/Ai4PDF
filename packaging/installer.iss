#ifndef AppVersion
  #define AppVersion "1.1.1"
#endif
#ifndef InstallerAppId
  #define InstallerAppId "{{C65AE3F2-8B1D-4DB1-9CA1-8E28116A449E}"
#endif
#ifndef InstallerFilename
  #define InstallerFilename "Ai4PDF-" + AppVersion + "-windows-x64-setup"
#endif
#define ProjectRoot AddBackslash(SourcePath) + ".."

[Setup]
AppId={#InstallerAppId}
AppName=Ai4PDF
AppVersion={#AppVersion}
AppVerName=Ai4PDF {#AppVersion}
AppPublisher=Teslajia
AppPublisherURL=https://github.com/Teslajia
DefaultDirName={localappdata}\Programs\Ai4PDF
DefaultGroupName=Ai4PDF
DisableProgramGroupPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ProjectRoot}\release
OutputBaseFilename={#InstallerFilename}
SetupIconFile={#ProjectRoot}\static\app-icon.ico
UninstallDisplayIcon={app}\Ai4PDF.exe
LicenseFile={#ProjectRoot}\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=Ai4PDF · PDF_AI助手

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesetraditional"; MessagesFile: "compiler:Languages\ChineseTraditional.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#ProjectRoot}\packaging\library-location.ps1"; Flags: dontcopy
Source: "{#ProjectRoot}\dist\Ai4PDF\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\Ai4PDF"; Filename: "{app}\Ai4PDF.exe"; Tasks: desktopicon
Name: "{group}\Ai4PDF"; Filename: "{app}\Ai4PDF.exe"
Name: "{group}\{cm:UninstallProgram,Ai4PDF}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\Ai4PDF.exe"; Description: "{cm:LaunchProgram,Ai4PDF}"; Flags: nowait postinstall skipifsilent; Check: LibraryReady

; Personal data live outside {app}. Never remove %LOCALAPPDATA%\Ai4PDF on uninstall.

[CustomMessages]
LibraryTitle=Local document library
LibrarySubtitle=Where should PDFs, annotations and translations be stored?
LibraryDescription=Choose an empty folder or an existing Ai4PDF library. Documents stay here after upgrades or uninstall. Ordinary PDF folders are not imported automatically.
LibraryExisting=An existing library was found and will be preserved. To move its documents, use Settings > Library migration after installation.
LibraryEnvironment=The library location is managed by AI4PDF_DATA or PAPERDESK_DATA. This installation will keep that setting.
LibraryPath=Document library folder:
LibraryError=Unable to use this library location:
LibrarySaveError=The program was installed, but the library setting could not be saved. Close Ai4PDF, check the folder permissions, then run this installer again.
chinesesimplified.LibraryTitle=本地文档库位置
chinesesimplified.LibrarySubtitle=选择 PDF、批注和译文的保存文件夹
chinesesimplified.LibraryDescription=请选择空文件夹，或已有的 Ai4PDF 文档库。升级、卸载均保留这里的文档。普通 PDF 文件夹不会自动导入。
chinesesimplified.LibraryExisting=检测到已有文档库，本次安装将保留原位置和资料。如需移动文档，请安装后使用「设置 → 文档库位置迁移」。
chinesesimplified.LibraryEnvironment=文档库由 AI4PDF_DATA 或 PAPERDESK_DATA 环境变量指定，本次安装将保留该设置。
chinesesimplified.LibraryPath=文档库文件夹：
chinesesimplified.LibraryError=无法使用此文档库位置：
chinesesimplified.LibrarySaveError=程序已安装，但文档库位置未保存成功。请退出 Ai4PDF、检查文件夹权限后重新运行安装程序。
chinesetraditional.LibraryTitle=本機文件庫位置
chinesetraditional.LibrarySubtitle=選擇 PDF、註解和譯文的儲存資料夾
chinesetraditional.LibraryDescription=請選擇空資料夾，或現有的 Ai4PDF 文件庫。升級、解除安裝均保留這裡的文件。一般 PDF 資料夾不會自動匯入。
chinesetraditional.LibraryExisting=偵測到現有文件庫，本次安裝將保留原位置和資料。如需移動文件，請安裝後使用「設定 → 文件庫位置遷移」。
chinesetraditional.LibraryEnvironment=文件庫由 AI4PDF_DATA 或 PAPERDESK_DATA 環境變數指定，本次安裝將保留該設定。
chinesetraditional.LibraryPath=文件庫資料夾：
chinesetraditional.LibraryError=無法使用此文件庫位置：
chinesetraditional.LibrarySaveError=程式已安裝，但文件庫位置未儲存成功。請結束 Ai4PDF、檢查資料夾權限後重新執行安裝程式。
japanese.LibraryTitle=ローカル文書ライブラリ
japanese.LibrarySubtitle=PDF、注釈、翻訳の保存フォルダーを選択
japanese.LibraryDescription=空のフォルダー、または既存の Ai4PDF ライブラリを選択してください。更新・アンインストール後も文書を保持します。通常の PDF フォルダーは自動で取り込まれません。
japanese.LibraryExisting=既存のライブラリを保持します。文書を移動する場合は、インストール後に「設定」のライブラリ移行機能をご利用ください。
japanese.LibraryEnvironment=AI4PDF_DATA または PAPERDESK_DATA 環境変数で指定された場所を保持します。
japanese.LibraryPath=ライブラリフォルダー：
japanese.LibraryError=このライブラリの場所を使用できません：
japanese.LibrarySaveError=ライブラリの場所を保存できませんでした。Ai4PDF を終了し、フォルダーの権限を確認して再インストールしてください。
korean.LibraryTitle=로컬 문서 라이브러리 위치
korean.LibrarySubtitle=PDF, 주석, 번역을 저장할 폴더 선택
korean.LibraryDescription=빈 폴더 또는 기존 Ai4PDF 라이브러리를 선택하세요. 업데이트하거나 제거해도 문서는 유지됩니다. 일반 PDF 폴더는 자동으로 가져오지 않습니다.
korean.LibraryExisting=기존 라이브러리 위치와 문서를 유지합니다. 문서를 옮기려면 설치 후 설정의 라이브러리 이전 기능을 사용하세요.
korean.LibraryEnvironment=AI4PDF_DATA 또는 PAPERDESK_DATA 환경 변수로 지정된 위치를 유지합니다.
korean.LibraryPath=라이브러리 폴더:
korean.LibraryError=이 라이브러리 위치를 사용할 수 없습니다:
korean.LibrarySaveError=라이브러리 위치를 저장하지 못했습니다. Ai4PDF를 종료하고 폴더 권한을 확인한 후 설치 프로그램을 다시 실행하세요.

[Code]
var
  LibraryPage: TInputDirWizardPage;
  LibraryConfigRoot, LibraryInitialPath, LibraryMode, LibraryResultFile: String;
  LibraryError, LibraryRequestedPath: String;
  LibrarySaveFailed: Boolean;

function QuoteArgument(const Value: String): String;
var
  I, Slashes: Integer;
begin
  Result := '"';
  Slashes := 0;
  for I := 1 to Length(Value) do begin
    if Value[I] = '\' then
      Slashes := Slashes + 1
    else begin
      if Value[I] = '"' then
        Result := Result + StringOfChar('\', 2 * Slashes + 1) + '"'
      else
        Result := Result + StringOfChar('\', Slashes) + Value[I];
      Slashes := 0;
    end;
  end;
  Result := Result + StringOfChar('\', 2 * Slashes) + '"';
end;

function LibraryHelper(const Mode: String): Boolean;
var
  Args: String;
  ExitCode: Integer;
begin
  DeleteFile(LibraryResultFile);
  Args := '-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' +
    QuoteArgument(ExpandConstant('{tmp}\library-location.ps1')) +
    ' -Mode ' + Mode + ' -ConfigRoot ' + QuoteArgument(LibraryConfigRoot) +
    ' -ResultFile ' + QuoteArgument(LibraryResultFile);
  if Mode <> 'Inspect' then
    Args := Args + ' -LibraryPath ' + QuoteArgument(LibraryPage.Values[0]) +
      ' -InstallDir ' + QuoteArgument(WizardDirValue) +
      ' -ExpectedPath ' + QuoteArgument(LibraryInitialPath) +
      ' -ExpectedMode ' + QuoteArgument(LibraryMode);
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    Args, '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
  Result := Result and (ExitCode = 0) and FileExists(LibraryResultFile);
  LibraryError := GetIniString('Library', 'Message', 'Windows PowerShell could not validate the library setting.', LibraryResultFile);
end;

procedure InitializeWizard;
var
  Description: String;
begin
  LibraryConfigRoot := GetEnv('AI4PDF_HOME');
  if LibraryConfigRoot = '' then begin
    LibraryConfigRoot := GetEnv('LOCALAPPDATA');
    if LibraryConfigRoot = '' then LibraryConfigRoot := ExpandConstant('{localappdata}');
    LibraryConfigRoot := AddBackslash(LibraryConfigRoot) + 'Ai4PDF';
  end;
  LibraryResultFile := ExpandConstant('{tmp}\ai4pdf-library.ini');
  ExtractTemporaryFile('library-location.ps1');
  if not LibraryHelper('Inspect') then
    RaiseException(CustomMessage('LibraryError') + #13#10 + LibraryError);
  LibraryMode := GetIniString('Library', 'Mode', '', LibraryResultFile);
  LibraryInitialPath := GetIniString('Library', 'Path', '', LibraryResultFile);
  Description := CustomMessage('LibraryDescription');
  if LibraryMode = 'existing' then Description := CustomMessage('LibraryExisting');
  if LibraryMode = 'environment' then Description := CustomMessage('LibraryEnvironment');
  LibraryPage := CreateInputDirPage(wpSelectDir, CustomMessage('LibraryTitle'),
    CustomMessage('LibrarySubtitle'), Description, False, 'Ai4PDF Library');
  LibraryPage.Add(CustomMessage('LibraryPath'));
  LibraryRequestedPath := ExpandConstant('{param:LIBRARYDIR|}');
  LibraryPage.Values[0] := LibraryInitialPath;
  if LibraryRequestedPath <> '' then LibraryPage.Values[0] := LibraryRequestedPath;
  if LibraryMode <> 'new' then begin
    LibraryPage.Edits[0].ReadOnly := True;
    LibraryPage.Buttons[0].Enabled := False;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = LibraryPage.ID then begin
    Result := LibraryHelper('Validate');
    if not Result then SuppressibleMsgBox(CustomMessage('LibraryError') + #13#10 + LibraryError,
      mbError, MB_OK, IDOK);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if not LibraryHelper('Validate') then Result := CustomMessage('LibraryError') + #13#10 + LibraryError;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine + CustomMessage('LibraryPath') + NewLine +
    Space + LibraryPage.Values[0] + NewLine + NewLine + MemoTasksInfo;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    LibrarySaveFailed := not LibraryHelper('Commit');
    if LibrarySaveFailed then SuppressibleMsgBox(CustomMessage('LibrarySaveError') + #13#10 + LibraryError,
      mbError, MB_OK, IDOK);
  end;
end;

function LibraryReady: Boolean;
begin
  Result := not LibrarySaveFailed;
end;

function GetCustomSetupExitCode: Integer;
begin
  Result := 0;
  if LibrarySaveFailed then Result := 12;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and LibrarySaveFailed then
    WizardForm.FinishedLabel.Caption := CustomMessage('LibrarySaveError') + #13#10 + LibraryError;
end;
