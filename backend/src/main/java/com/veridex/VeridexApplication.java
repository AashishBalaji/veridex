package com.veridex;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

import java.util.TimeZone;

@SpringBootApplication
public class VeridexApplication {

    // Pin the JVM default timezone rather than inherit whatever the
    // host happens to export. The pgjdbc driver sends this as a
    // session `SET TimeZone` on every new connection, and some hosts
    // export legacy zone-id aliases (e.g. "Asia/Calcutta") that this
    // project's Postgres version doesn't recognize, which fails every
    // connection outright -- confirmed directly: that exact failure
    // is what surfaced this, caught by the JUnit tests that run
    // against a real local database rather than a mock. A static
    // initializer (not a line in main()) so it also takes effect
    // under @SpringBootTest, which never calls main().
    static {
        TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
    }

    public static void main(String[] args) {
        SpringApplication.run(VeridexApplication.class, args);
    }
}
