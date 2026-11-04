PACKAGE=main
EXENAME=Taludas.Anno.117.Map.Editor
VENVNAME=tamper

##############################################################################
# do this while not in venv
venv:
	python -m venv .$(VENVNAME).venv

venv.clean:
	-cmd /c rd /s /q .$(VENVNAME).venv



##############################################################################
# do these while in venv
run: libs.quiet
	py $(PACKAGE).py


# libs make targets ###########################
libs: requirements.txt
	pip install -r requirements.txt

libs.quiet: requirements.txt
	pip install -q -r requirements.txt

libs.clean:
	pip uninstall -r requirements.txt


# from command line
#		python main.py
#
# exe make targets ###########################
# data/ icons the legacy build already pulled in.
#
# The three [Map] template folders have to be bundled too: mod_exporter reads the
# region .a7t (terrain source), assets.xml, modinfo.json and texts_english.xml
# out of them at export time, and config.resource_path() resolves to sys._MEIPASS
# in a frozen build - so without these the exe starts fine and only fails once
# you export. The DLC03 folder also carries the Aegyptus block of assets.xml and
# the Egypt .a7t/.a7te. $$ escapes the $ so make does not expand $ModName.
MAPDIR       = [Map] $$ModName (TAMPER)
MAPDIR_ENL   = [Map] $$ModName Enlarged (TAMPER)
MAPDIR_DLC03 = [Map] $$ModName Enlarged DLC03 (TAMPER)

exe: libs
	pyinstaller --onefile --windowed --add-data "data;data" --add-data "_version.py;." --add-data "$(MAPDIR);$(MAPDIR)" --add-data "$(MAPDIR_ENL);$(MAPDIR_ENL)" --add-data "$(MAPDIR_DLC03);$(MAPDIR_DLC03)" --icon="app_icon.ico" --version-file="file_version_info.txt" --name $(EXENAME) $(PACKAGE).py

exe.clean:
	-cmd /c rd /s /q build
	-cmd /c rd /s /q dist
	-cmd /c del /q $(EXENAME).spec


# general make targets ###########################

all: libs exe

all.clean: libs.clean exe.clean

clean: all.clean