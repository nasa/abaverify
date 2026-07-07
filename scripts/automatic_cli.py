
import argparse
import os
import abaverify as av

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Automatically run abaverify verification tests.')
    parser.add_argument('testDirectory', help='Directory containing the tests.')
    parser.add_argument("-f", "--tr-file-name", default='test_runner.py', help="Name of the test runner file to look for in each test directory (default is 'test_runner.py')")
    parser.add_argument("-o", "--outputDirectory", default='testOutput', help="Directory where job is run and output is generated")
    parser.add_argument("-a", "--archiveDirectory", default='archivedTestResults', help="Directory for archiving results")
    parser.add_argument("-c", "--abaqusCommand", default='abaqus', help="Command to run Abaqus (default is 'abaqus')")
    parser.add_argument("-C", "--cpus", type=int, default=1, help="Number of CPUs to use for running the tests (default is 1)")
    parser.add_argument("-t", "--tests", nargs='*', default=[], help="List of specific tests to run (default is all tests)")
    parser.add_argument("-u", "--usub_lib_dir", default='', help="Directory for compiled binaries")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print verbose output")
    parser.add_argument("--report_img_html", default="", help="File containing image html to include in the report")
    parser.add_argument("--reportExistingResults", action="store_true", help="Run the report generation on existing test results in the output directory instead of running the tests")
    parser.add_argument("--reportFailedTestsOnly", action="store_true", help="Only include failed tests in the html report")
    args = parser.parse_args()

    # Initialize the automatic tester
    av_auto = av.Automatic(test_directory=args.testDirectory,
                            archive_directory=args.archiveDirectory,
                            test_output_directory=args.outputDirectory,
                            usub_lib_dir=args.usub_lib_dir,
                            force_tests=True,
                            tests_to_run=args.tests,
                            test_runner_file_name=args.tr_file_name,
                            verbose=args.verbose,
                            cpus=args.cpus,
                            abaqus_cmd=args.abaqusCommand)


    # Run the tests
    if args.reportExistingResults:
        av_auto._setBaseFileName(name=args.reportExistingResults)
        path_to_json = os.path.join(av_auto.archive_directory, av_auto.base_file_name + ".json")
        av_auto.test_report = av.TestReport.fromArchivedResult(path_to_json)
        result = True
    else:
        result = av_auto.run()

    image_html = ""
    if args.report_img_html:
            with open(args.report_img_html, 'r') as f:
                image_html = f.read()
        

    # Report the results
    if result:
        av_auto.generateReport(template='template_email_summary', failed_only=args.reportFailedTestsOnly, image_html=image_html)
