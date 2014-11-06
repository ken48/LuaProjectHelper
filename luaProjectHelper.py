import os, re, logging, threading, string
import sublime, sublime_plugin

####################################################################################################
class GotoLuaDefinition(sublime_plugin.TextCommand):
	defList = []

	def run(self, edit):
		wordRegion = self.view.word(self.view.sel()[0].end())
		word = self.view.substr(wordRegion)
		if word is None or word == '':
			return

		if len(LuaProject.autoCompletionList) == 0:
			ProjectDBGenerator.update()

		self.defList = []
		defShowList = []

		for module, obj in LuaProject.projectDictionary.items():
			for name, data in obj.items():
				# name = func, data[0] - line, data[1] - args, data[2] - table
				if word == name:
					defShowList.append(module + ' : ' + str(data[0]))
					self.defList.append(LuaProject.projectFileDic[module] + ':' + str(data[0]))
					
		window = sublime.active_window()
		listSize = len(self.defList)
		if listSize == 1:
			window.open_file(self.defList[0], sublime.ENCODED_POSITION)
		elif listSize > 0:
			window.show_quick_panel(defShowList, self.onChoice)
		else:
			sublime.status_message('Unable to find definition for \'' + word + '\'')

	def onChoice(self, value):
		if value >= 0 and value < len(self.defList):
			sublime.active_window().open_file(self.defList[value], sublime.ENCODED_POSITION)


####################################################################################################
# Auto complet event
class LuaProjectAutoCompletion(sublime_plugin.EventListener):

	tableNameFindProg = re.compile('\w+:\w*$')
	tableNameFindDotProg = re.compile('\w+.\w*$')

	# Invoked when user toggles a side_bar or removes folder.
	# Unfortunately there is no command on "add folder" event :(
	def on_window_command(self, window, command_name, args):
		if command_name == "toggle_side_bar" or command_name == "remove_folder":
			ProjectDBGenerator.update()

	# Invoked when user saves a file
	def on_post_save(self, view):
		ProjectDBGenerator.update()

	# Change autocomplete suggestions
	def on_query_completions(self, view, prefix, locations):
		curFile = view.file_name()
		defCompletions = [(item, item) for sublist in [view.extract_completions(prefix)]
															for item in sublist if len(item) > 3]

		complFlags = sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS

		if ProjectDBGenerator.testFileExt(curFile):
			if len(LuaProject.autoCompletionList) == 0:
				ProjectDBGenerator.update()
			else:
				caretPos = view.sel()[0].end()
				linePos = view.line(caretPos)
				curline = view.substr(linePos)
				curline = curline[:view.rowcol(caretPos)[1]]
				matchTable = self.tableNameFindProg.search(curline)
				sep = ':'
				if matchTable is None:
					matchTable = self.tableNameFindDotProg.search(curline)
					sep = '.'

				if matchTable:
					tableCompls = LuaProject.getTableCompletionList(matchTable.group().split(sep, 1)[0])
					if tableCompls is not None and len(tableCompls) > 0:
						return(tableCompls, complFlags)
				
			ret = []
			ret.extend(LuaProject.autoCompletionList)
			ret.extend(defCompletions)
			return (ret, complFlags)

		return (defCompletions, complFlags)


####################################################################################################
class LuaProject:
	projectFileDic = {}
	projectDictionary = {}
	autoCompletionList = []

	def clear():
		LuaProject.projectFileDic = {}
		LuaProject.projectDictionary = {}
		LuaProject.autoCompletionList = []

	def getTableCompletionList(tableName):
		tableList = []
		if tableName == '':
			return tableList

		for module, obj in LuaProject.projectDictionary.items():
			for name, data in obj.items():
				if tableName == data[2]:
					tableList.append((name + '\t' + module, name + data[1]))
		return tableList


####################################################################################################
class ProjectDBGenerator:
	funcFindProg = re.compile('function\s+(.+?)\s*\)')
	wsProg = re.compile(r'\s+')
	reMethodArgs = re.compile("\((.*)\)")

	def update():
		LuaProject.clear()
		fileDic = {}

		if len(sublime.active_window().folders()) > 0:
			projectFolderList = sublime.active_window().folders()
		
			for path in projectFolderList:
				if os.path.isdir(path):
					fileDic.update(ProjectDBGenerator.getFileDic(path))

		LuaProject.projectFileDic = fileDic
		LuaProject.projectDictionary = ProjectDBGenerator.genProjectDictionary(fileDic)

		for module, obj in LuaProject.projectDictionary.items():
			for name, data in obj.items():
				LuaProject.autoCompletionList.append((name + '\t' + module, name + data[1]))

		LuaProject.autoCompletionList.sort()

	#-----------------------------------------------------------------------------------------------
	def getFileDic(path):
		fileDic = {}
		for root, dirs, files in os.walk(path):
			for name in files:
				if ProjectDBGenerator.testFileExt(name):
					fileDic[name.split('.', 1)[0]] = os.path.join(root, name)

		return fileDic

	#-----------------------------------------------------------------------------------------------
	def parseLuaFile(buf):
		fileDic = {}
		lineList = buf.splitlines()
		lineCounter = 0

		for line in lineList:
			lineCounter = lineCounter + 1
			funcs = ProjectDBGenerator.funcFindProg.findall(line)
			if len(funcs) > 0:
				for func in funcs:
					tableName = ''
					tableFuncList = func.split(':', 1)

					if len(tableFuncList) > 1:
						tableName = tableFuncList[0]
						fileDic[tableFuncList[0]] = [1, '', '']
						funcAndArgs = tableFuncList[1]
					else:
						dottedTableFunc = func.split('.', 1)
						if len(dottedTableFunc) > 1:
							tableName = dottedTableFunc[0]
							fileDic[dottedTableFunc[0]] = [1, '', '']
							funcAndArgs = dottedTableFunc[1]
						else:
							funcAndArgs = tableFuncList[0]

					#split func signature & argument list
					funcAndArgsList = funcAndArgs.split('(', 1)
					funcName = ProjectDBGenerator.wsProg.sub('', funcAndArgsList[0])

					if len(funcName) > 0:
						try:
							if funcAndArgsList[1] is None or funcAndArgsList[1] == '':
								selectedArgsList = '()'
							else:
								selectedArgsList = re.sub( ProjectDBGenerator.reMethodArgs , '(${1:\\1})' , '(' + funcAndArgsList[1] + ')' )

							fileDic[funcName] = [lineCounter, selectedArgsList, tableName]
						except IndexError:
							fileDic[funcName] = [lineCounter, '', tableName]
		return fileDic

	#-----------------------------------------------------------------------------------------------
	def genProjectDictionary(fDic):
		projDic = {}
		for name, path in fDic.items():
			with open(path, 'r') as fileContent:
				try:
					buf = fileContent.read()
				except:
					buf = ''

				projDic[name] = ProjectDBGenerator.parseLuaFile(buf)

		return projDic

	#-----------------------------------------------------------------------------------------------
	def testFileExt(file):
		return file.endswith('.lua')