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
exe: libs
	pyinstaller --onefile --windowed --add-data "data;data" --add-data "_version.py;." --icon="app_icon.ico" --version-file="file_version_info.txt" --name $(EXENAME) $(PACKAGE).py

exe.clean:
	-cmd /c rd /s /q build
	-cmd /c rd /s /q dist
	-cmd /c del /q $(EXENAME).spec


# general make targets ###########################

all: libs exe

all.clean: libs.clean exe.clean

clean: all.clean