#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# import from future to make Python2 behave like Python3
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import *
from io import open
# end of from future import

try:
    # Python 2
    basestring
except NameError:
    # Python 3 or newer
    basestring = str


class _BaseSimulator(object):
    """ Basic class to simulate a Modelica model.

    :param modelName: The name of the Modelica model.
    :param outputDirectory: An optional output directory.
    :param packagePath: An optional path where the Modelica ``package.mo`` file is located.

    If the parameter ``outputDirectory`` is specified, then the
    output files and log files will be moved to this directory
    when the simulation is completed.
    Outputs from the python functions will be written to ``outputDirectory/BuildingsPy.log``.

    If the parameter ``packagePath`` is specified, the Simulator will copy this directory
    and all its subdirectories to a temporary directory when running the simulations.

    .. note:: Up to version 1.4, the environmental variable ``MODELICAPATH``
              has been used as the default value. This has been changed as
              ``MODELICAPATH`` can have multiple entries in which case it is not
              clear what entry should be used.
    """

    def __init__(
            self,
            modelName,
            outputDirectory,
            packagePath,
            outputFileList,
            logFileList):
        import buildingspy.io.reporter as reporter
        import os

        # Set log file name for python script
        logFilNam = os.path.join(outputDirectory, "BuildingsPy.log")

        # Check if the packagePath parameter is correct
        self._packagePath = None
        if packagePath is None:
            self.setPackagePath(os.path.abspath('.'))
        else:
            self.setPackagePath(packagePath)

        self.modelName = modelName
        self._parameters_ = {}
        self._modelModifiers_ = list()

        self._simulator_ = {}

        self._outputDir_ = outputDirectory

        self._simulateDir_ = None

        self._outputFileList = outputFileList
        self._logFileList = logFileList

        # This call is needed so that the reporter can write to the working directory
        self._createDirectory(outputDirectory)

#        # This call is needed so that the reporter can write to the working directory
#        self._createDirectory(outputDirectory)
#        self._preProcessing_ = list()
#        self._postProcessing_ = list()
#        self._parameters_ = {}
#        self._modelModifiers_ = list()
        self.setStartTime(None)
        self.setStopTime(None)
        self.setTolerance(1E-6)
        self.setNumberOfIntervals()
#        self.setSolver("radau")
        self.setTimeOut(-1)
        self._MODELICA_EXE = None
        self._reporter = reporter.Reporter(fileName=logFilNam)
        self._showProgressBar = False
        self._showGUI = False
        self._exitSimulator = True

    def setPackagePath(self, packagePath):
        """ Set the path specified by ``packagePath``.

        :param packagePath: The path where the Modelica package to be loaded is located.

        It first checks whether the path exists and whether it is a directory.
        If both conditions are satisfied, the path is set.
        Otherwise, a ``ValueError`` is raised.
        """
        import os

        # Check whether the package Path parameter is correct
        if not os.path.exists(packagePath):
            msg = "Argument packagePath=%s does not exist." % packagePath
            raise ValueError(msg)

        if not os.path.isdir(packagePath):
            msg = "Argument packagePath=%s must be a directory " % packagePath
            msg += "containing a Modelica package."
            raise ValueError(msg)

        # All the checks have been successfully passed
        self._packagePath = packagePath

    def addParameters(self, dictionary):
        """Adds parameter declarations to the simulator.

        :param dictionary: A dictionary with the parameter values

        Usage: Type
           >>> from buildingspy.simulate.Simulator import Simulator
           >>> s=Simulator("myPackage.myModel", "dymola", packagePath="buildingspy/tests/MyModelicaLibrary")
           >>> s.addParameters({'PID.k': 1.0, 'valve.m_flow_nominal' : 0.1})
           >>> s.addParameters({'PID.t': 10.0})

        This will add the three parameters ``PID.k``, ``valve.m_flow_nominal``
        and ``PID.t`` to the list of model parameters.

        For parameters that are arrays, use a syntax such as
           >>> from buildingspy.simulate.Simulator import Simulator
           >>> s = Simulator("MyModelicaLibrary.Examples.Constants", "dymola", packagePath="buildingspy/tests/MyModelicaLibrary")
           >>> s.addParameters({'const1.k' : [2, 3]})
           >>> s.addParameters({'const2.k' : [[1.1, 1.2], [2.1, 2.2], [3.1, 3.2]]})

        Do not use curly brackets for the values of parameters, such as
        ``s.addParameters({'const1.k' : {2, 3}})``
        as Python converts this entry to ``{'const1.k': set([2, 3])}``.

        """
        self._parameters_.update(dictionary)
        return

    def getParameters(self):
        """Returns a list of parameters as (key, value)-tuples.

        :return: A list of parameters as (key, value)-tuples.

        Usage: Type
           >>> from buildingspy.simulate.Simulator import Simulator
           >>> s=Simulator("myPackage.myModel", "dymola", packagePath="buildingspy/tests/MyModelicaLibrary")
           >>> s.addParameters({'PID.k': 1.0, 'valve.m_flow_nominal' : 0.1})
           >>> s.getParameters()
           [('PID.k', 1.0), ('valve.m_flow_nominal', 0.1)]
        """
        return list(self._parameters_.items())


    def addModelModifier(self, modelModifier):
        """Adds a model modifier.

        :param dictionary: A model modifier.

        Usage: Type
           >>> from buildingspy.simulate.Simulator import Simulator
           >>> s=Simulator("myPackage.myModel", "dymola", packagePath="buildingspy/tests/MyModelicaLibrary")
           >>> s.addModelModifier('redeclare package MediumA = Buildings.Media.IdealGases.SimpleAir')

        This method adds a model modifier. The modifier is added to the list
        of model parameters. For example, the above statement would yield the
        command
        ``simulateModel(myPackage.myModel(redeclare package MediumA = Buildings.Media.IdealGases.SimpleAir), startTime=...``

        """
        self._modelModifiers_.append(modelModifier)
        return


    def _createDirectory(self, directoryName):
        """ Creates the directory *directoryName*

        :param directoryName: The name of the directory

        This method validates the directory *directoryName* and if the
        argument is valid and write permissions exists, it creates the
        directory. Otherwise, a *ValueError* is raised.
        """
        import os

        if directoryName != '.':
            if len(directoryName) == 0:
                raise ValueError(
                    "Specified directory is not valid. Set to '.' for current directory.")
            # Try to create directory
            if not os.path.exists(directoryName):
                os.makedirs(directoryName)
            # Check write permission
            if not os.access(directoryName, os.W_OK):
                raise ValueError("Write permission to '" + directoryName + "' denied.")

    def getOutputDirectory(self):
        """Returns the name of the output directory.

        :return: The name of the output directory.

        """
        return self._outputDir_

    def setOutputDirectory(self, outputDirectory):
        """Sets the name of the output directory.

        :return: The name of the output directory.

        """
        self._outputDir_ = outputDirectory
        return self._outputDir_

    def getPackagePath(self):
        """Returns the path of the directory containing the Modelica package.

        :return: The path of the Modelica package directory.

        """
        return self._packagePath


    def setStartTime(self, t0):
        """Sets the start time.

        :param t0: The start time of the simulation in seconds.

        The default start time is 0.
        """
        self._simulator_.update(t0=t0)
        return

    def setStopTime(self, t1):
        """Sets the start time.

        :param t1: The stop time of the simulation in seconds.

        The default stop time is 1.
        """
        self._simulator_.update(t1=t1)
        return

    def setTolerance(self, eps):
        """Sets the solver tolerance.

        :param eps: The solver tolerance.

        The default solver tolerance is 1E-6.
        """
        self._simulator_.update(eps=eps)
        return

    def setSolver(self, solver):
        """Sets the solver.

        :param solver: The name of the solver.

        The default solver is *radau*.
        """
        self._simulator_.update(solver=solver)
        return

    def setNumberOfIntervals(self, n=500):
        """Sets the number of output intervals.

        :param n: The number of output intervals.

        The default is unspecified, which defaults to 500.
        """
        self._simulator_.update(numberOfIntervals=n)
        return

    def _deleteFiles(self, fileList):
        """ Deletes the output files of the simulator.

        :param fileList: List of files to be deleted.

        """
        import os

        for fil in fileList:
            try:
                if os.path.exists(fil):
                    os.remove(fil)
            except OSError as e:
                self._reporter.writeError("Failed to delete '" + fil + "' : " + e.strerror)

    def _deleteTemporaryDirectory(self, worDir):
        """ Deletes the working directory.
            If this function is invoked with `worDir=None`, then it immediately returns.

        :param srcDir: The name of the working directory.

        """
        import shutil
        import os

        if worDir is None:
            return

        # For Dymola, walk one level up, since we appended the name of the current directory
        # to the name of the working directory
        if self._simulator_ is 'dymola':
            dirNam = os.path.split(worDir)[0]
        else:
            dirNam = worDir

        # Make sure we don't delete a root directory
        if dirNam.find('tmp-simulator-') == -1:
            self._reporter.writeError(
                "Failed to delete '" +
                dirNam +
                "' as it does not seem to be a valid directory name.")
        else:
            try:
                if os.path.exists(worDir):
                    shutil.rmtree(dirNam)
            except IOError as e:
                self._reporter.writeError("Failed to delete '" +
                                          worDir + ": " + e.strerror)

    def deleteSimulateDirectory(self):
        """ Deletes the simulate directory. Can be called when simulation failed.
        """
        self._deleteTemporaryDirectory(self._simulateDir_)

    def _isExecutable(self, program):
        import os
        import platform

        def is_exe(fpath):
            return os.path.exists(fpath) and os.access(fpath, os.X_OK)

        # Add .exe, which is needed on Windows 7 to test existence
        # of the program
        if platform.system() == "Windows":
            program = program + ".exe"

        if is_exe(program):
            return True
        else:
            for path in os.environ["PATH"].split(os.pathsep):
                exe_file = os.path.join(path, program)
                if is_exe(exe_file):
                    return True
        return False

    def _create_worDir(self):
        """ Create working directory
        """
        import os
        import tempfile
        import getpass
        curDir = os.path.abspath(self._packagePath)
        ds = curDir.split(os.sep)
        dirNam = ds[len(ds) - 1]
        worDir = os.path.join(tempfile.mkdtemp(
            prefix='tmp-simulator-' + getpass.getuser() + '-'), dirNam)
        return worDir

    def setTimeOut(self, sec):
        """Sets the time out after which the simulation will be killed.

        :param sec: The time out after which the simulation will be killed.

        The default value is -1, which means that the simulation will
        never be killed.
        """
        self._simulator_.update(timeout=sec)
        return

    def setResultFile(self, resultFile):
        """Sets the name of the result file (without extension).

        :param resultFile: The name of the result file (without extension).

        """
        # If resultFile=aa.bb.cc, then split returns [aa, bb, cc]
        # This is needed to get the short model name
#        rs = resultFile.split(".")
#        self._simulator_.update(resultFile=rs[len(rs) - 1])
        self._simulator_.update(resultFile=resultFile)
        return

    def _declare_parameters(self):
        """ Declare list of parameters
        """
        def to_modelica(arg):
            """ Convert to Modelica array.
            """
            # Check for strings and booleans
            if isinstance(arg, basestring):
                return '\\"' + arg + '\\"'
            elif isinstance(arg, bool):
                if arg is True:
                    return 'true'
                else:
                    return 'false'
            try:
                return '{' + ", ".join(to_modelica(x) for x in arg) + '}'
            except TypeError:
                return repr(arg)
        dec = list()

        for k, v in list(self._parameters_.items()):
            # Dymola requires vectors of parameters to be set in the format
            # p = {1, 2, 3} rather than in the format of python arrays, which
            # is p = [1, 2, 3].
            # Hence, we convert the value of the parameter if required.
            s = to_modelica(v)
            dec.append('{param}={value}'.format(param=k, value=s))

        return dec

    def _runSimulation(self, cmd, timeout, directory, env=None):
        """Runs a model translation or simulation.

        :param cmd: Array with command arguments
        :param timeout: Time out in seconds
        :param directory: The working directory

        """

        import sys
        import subprocess
        import time
        import datetime

        # Check if executable is on the path
        if not self._isExecutable(cmd[0]):
            print(("Error: Did not find executable '", cmd[0], "'."))
            print("       Make sure it is on the PATH variable of your operating system.")
            exit(3)
        # Run command
        try:
            self._simulationStartTime = datetime.datetime.now()
            if env is None:
                pro = subprocess.Popen(args=cmd,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       shell=False,
                                       cwd=directory)
            else:
                pro = subprocess.Popen(args=cmd,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE,
                                       shell=False,
                                       cwd=directory,
                                       env=env)

            killedProcess = False
            if timeout > 0:
                while pro.poll() is None:
                    time.sleep(0.01)
                    elapsedTime = (datetime.datetime.now() - self._simulationStartTime).seconds

                    if elapsedTime > timeout:
                        # First, terminate the process. Then, if it is still
                        # running, kill the process

                        if self._showProgressBar and not killedProcess:
                            killedProcess = True
                            # This output needed because of the progress bar
                            sys.stdout.write("\n")
                            self._reporter.writeError("Terminating simulation in " +
                                                      directory + ".")
                            pro.terminate()
                        else:
                            self._reporter.writeError("Killing simulation in " +
                                                      directory + ".")
                            pro.kill()
                    else:
                        if self._showProgressBar:
                            fractionComplete = float(elapsedTime) / float(timeout)
                            self._printProgressBar(fractionComplete)

            else:
                pro.wait()
            # This output is needed because of the progress bar
            if self._showProgressBar and not killedProcess:
                sys.stdout.write("\n")

            if not killedProcess:
                std_out = pro.stdout.read()
                if len(std_out) > 0:
                    self._reporter.writeOutput(f"*** Standard output stream from simulation:\n{std_out}")

                std_err = pro.stderr.read()
                if len(std_err) > 0:
                    if pro.returncode != 0:
                        self._reporter.writeError(f"*** Standard error stream from simulation:\n{std_err}")
                    else:
                        # Optimica writes warnings such as missing IPOPT installation to stderr,
                        # but in this situation we want to continue unless it returns a non-zero exit code.
                        self._reporter.writeOutput(f"*** Standard error stream from simulation:\n{std_err}")
            else:
                self._reporter.writeError(f"Killed process as it computed longer than {str(timeout)} seconds.")

            pro.stdout.close()
            pro.stderr.close()

        except OSError as e:
            print(("Execution of ", cmd, " failed:", e))

    def _printProgressBar(self, fractionComplete):
        """Prints a progress bar to the console.

        :param fractionComplete: The fraction of the time that is completed.

        """
        import sys
        nInc = 50
        count = int(nInc * fractionComplete)
        proBar = "|"
        for i in range(nInc):
            if i < count:
                proBar += "-"
            else:
                proBar += " "
        proBar += "|"
        print((proBar, int(fractionComplete * 100), "%\r",))
        sys.stdout.flush()

    def _copyResultFiles(self, srcDir):
        """ Copies the output and log files of the simulator.

        :param srcDir: The source directory of the files

        """
        import shutil
        import os
        import time

        for root, dirs, files in os.walk(srcDir):
          for name in files:
            filename = os.path.join(root, name)
            if os.path.getmtime(filename) > self._simulationStartTime.timestamp():
                relativeName = filename[len(srcDir)+1:]
                self.__copy_file(filename, os.path.join(self._outputDir_, relativeName))

    def __copy_file(self, srcFil, newFil):
        import os
        import shutil

        try:
            if os.path.exists(srcFil):
                shutil.copy(srcFil, newFil)
        except IOError as e:
            self._reporter.writeError("Failed to copy '" +
                                      srcFil + "' to '" + newFil +
                                      "; : " + e.strerror)


    def deleteOutputFiles(self):
        """ Deletes the output files of the simulator.
        """
        self._deleteFiles(self._outputFileList)
        self._deleteFiles([self._simulator_.get('resultFile') + "_result.mat"])

    def deleteLogFiles(self):
        """ Deletes the log files of the Python simulator, e.g. the
            files ``BuildingsPy.log``, ``run.mos`` and ``simulator.log``.
        """
        self._deleteFiles(self._logFileList)